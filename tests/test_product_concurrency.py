"""Controlled concurrent transports prove account deletion and save boundaries.

All model outputs here are deterministic test doubles, never live-model evidence.
"""
import asyncio
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agent.errors import RuntimeFailure
from app.agent.orchestrator import AgentOrchestrator
from app.config.settings import Settings
from app.product import card_store
from app.product.card_store import CardStore
from app.product.main import create_app
from app.schemas.workflow import StopReason
from test_product_loop import StructuredDouble, confirm, journey, register, save


def app_config(tmp_path):
    return Settings(_env_file=None, product_data_dir=tmp_path,
                    product_origin='https://testserver', product_cookie_secure=True)


@pytest.mark.parametrize('conflicting_payload', [False, True])
def test_concurrent_receipt_misses_are_serialized(tmp_path, monkeypatch, conflicting_payload):
    store = CardStore(tmp_path / 'cards.sqlite3')
    owner, operation = str(uuid4()), str(uuid4())
    request = dict(operation_id=operation, session_id=str(uuid4()), understanding_id='confirmed',
                   expected_revision=2, choice='next', keep_text='保留勇气', release_text='',
                   next_step='尝试表达', remember_for_future=True)
    store.list(owner)  # Initialize before intentionally synchronizing the receipt miss.
    original_replay = store.replay
    barrier = threading.Barrier(2)
    local = threading.local()

    def simultaneous_miss(*args):
        result = original_replay(*args)
        if not getattr(local, 'checked', False):
            local.checked = True
            assert result is None
            barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(store, 'replay', simultaneous_miss)

    def write(body):
        try:
            return store.save(owner, operation, body, fields={})
        except RuntimeFailure as error:
            return error.code

    second = {**request, 'next_step': '不同的内容'} if conflicting_payload else dict(request)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(write, body) for body in (request, second)]
        results = [future.result(timeout=15) for future in pending]
    cards = store.list(owner)
    assert len(cards) == 1
    if conflicting_payload:
        assert results.count('operation_id_conflict') == 1
        assert sum(isinstance(result, dict) for result in results) == 1
    else:
        assert results[0]['card_id'] == results[1]['card_id'] == cards[0]['card_id']
    with sqlite3.connect(store.path) as connection:
        assert connection.execute('SELECT count(*) FROM receipts').fetchone()[0] == 1


def test_delete_account_freezes_requests_during_disk_erasure(tmp_path, monkeypatch):
    app = create_app(app_config(tmp_path), model_factory=StructuredDouble)
    with TestClient(app, base_url='https://testserver') as client:
        headers = register(client)
        owner = client.get('/api/account/me').json()['user']['id']
        sid, reply = journey(client, headers)
        _, previous_save = save(client, headers, sid, confirm(client, headers, sid, reply['generated_understanding']))
        entered, release = threading.Event(), threading.Event()
        original = app.state.auth_store.delete_user

        def delayed_delete(user_id):
            entered.set()  # Card erasure has finished; user/session erasure is pending.
            assert release.wait(10)
            return original(user_id)

        monkeypatch.setattr(app.state.auth_store, 'delete_user', delayed_delete)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.delete, '/api/account/me', headers=headers)
            try:
                assert entered.wait(10)
                assert client.post('/api/support/sessions', json={}, headers=headers).status_code == 401
                assert client.post('/api/product/cards', json=previous_save, headers=headers).status_code == 401
                # Previously login -> logout -> login removed the frozen workspace,
                # allowing a new service to save cards after delete_owner had run.
                attempts = []
                fresh_headers = headers
                for _ in range(2):
                    response = client.post('/api/account/login', headers={'Origin': 'https://testserver'},
                        json=dict(username='tester_one', password='demo-password-123', consent=True))
                    if response.status_code == 200:
                        fresh_headers = {'Origin': 'https://testserver', 'x-csrf-token': response.json()['csrf_token']}
                    sign_out = client.post('/api/account/logout', headers=fresh_headers)
                    new_journey = client.post('/api/support/sessions', json={}, headers=fresh_headers)
                    attempts.append((response.status_code, sign_out.status_code, new_journey.status_code))
                assert attempts == [(401, 401, 401), (401, 401, 401)]
            finally:
                release.set()
            assert pending.result(timeout=10).status_code == 204
        assert app.state.card_store.list(owner) == []
        assert client.get('/api/account/me').json() == {'user': None}
        with sqlite3.connect(app.state.auth_store.path) as connection:
            assert connection.execute('SELECT count(*) FROM users').fetchone()[0] == 0
            assert connection.execute('SELECT count(*) FROM sessions').fetchone()[0] == 0


def test_admitted_save_finishes_before_account_disk_erasure(tmp_path, monkeypatch):
    app = create_app(app_config(tmp_path), model_factory=StructuredDouble)
    with TestClient(app, base_url='https://testserver') as client:
        headers = register(client)
        owner = client.get('/api/account/me').json()['user']['id']
        sid, reply = journey(client, headers)
        understood = confirm(client, headers, sid, reply['generated_understanding'])
        payload = dict(operation_id=str(uuid4()), session_id=sid,
            understanding_id=understood['understanding_id'], expected_revision=understood['revision'],
            choice='next', next_step='先写下一句想说的话', remember_for_future=True)
        saving, release, frozen, erased = (threading.Event() for _ in range(4))
        original_save = app.state.card_store.save
        original_delete = app.state.card_store.delete_owner
        original_signal = AgentOrchestrator._signal

        def delayed_save(*args, **kwargs):
            saving.set()
            assert release.wait(10)
            return original_save(*args, **kwargs)

        def tracked_delete(user_id):
            erased.set()
            return original_delete(user_id)

        def tracked_signal(record, reason):
            result = original_signal(record, reason)
            if reason == StopReason.SESSION_ENDED:
                frozen.set()
            return result

        monkeypatch.setattr(app.state.card_store, 'save', delayed_save)
        monkeypatch.setattr(app.state.card_store, 'delete_owner', tracked_delete)
        monkeypatch.setattr(AgentOrchestrator, '_signal', staticmethod(tracked_signal))
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending_save = pool.submit(client.post, '/api/product/cards', headers=headers, json=payload)
            assert saving.wait(10)
            pending_delete = pool.submit(client.delete, '/api/account/me', headers=headers)
            try:
                assert frozen.wait(10)
                assert not erased.is_set()
            finally:
                release.set()
            assert pending_save.result(timeout=10).status_code == 201
            assert pending_delete.result(timeout=10).status_code == 204
        assert app.state.card_store.list(owner) == []
        with sqlite3.connect(app.state.card_store.path) as connection:
            assert connection.execute('SELECT count(*) FROM receipts').fetchone()[0] == 0


def test_account_deletion_discards_cancellation_resistant_late_model(tmp_path, monkeypatch):
    class DelayedModel(StructuredDouble):
        def __init__(self):
            super().__init__()
            self.started = threading.Event()
            self.finished = threading.Event()

        async def generate_structured(self, **kwargs):
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                # Simulate an upstream transport returning content after cancellation.
                return await super().generate_structured(**kwargs)
            finally:
                self.finished.set()

    model = DelayedModel()
    app = create_app(app_config(tmp_path), model_factory=lambda: model)
    captured = []
    original = AgentOrchestrator.handle_message

    async def track_record(self, sid, request, transport):
        captured.append(self.sessions.require(sid))
        return await original(self, sid, request, transport)

    monkeypatch.setattr(AgentOrchestrator, 'handle_message', track_record)
    with TestClient(app, base_url='https://testserver') as client:
        headers = register(client)
        owner = client.get('/api/account/me').json()['user']['id']
        sid = client.post('/api/support/sessions', json={}, headers=headers).json()['session_id']
        payload = dict(content='虚构场景：讨论时没有说完', request_id=str(uuid4()), model_consent=True)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.post, f'/api/support/sessions/{sid}/messages', headers=headers, json=payload)
            assert model.started.wait(10)
            assert client.delete('/api/account/me', headers=headers).status_code == 204
            assert pending.result(timeout=10).status_code >= 400
        assert model.finished.wait(10)
        assert captured and not captured[0].session.messages
        assert not captured[0].understandings.entries
        assert captured[0].active_task is None
        assert app.state.card_store.list(owner) == []
        assert client.get(f'/api/support/sessions/{sid}').status_code == 401


def test_card_database_connection_is_closed_after_use(tmp_path, monkeypatch):
    opened = []
    original_connect = card_store.sqlite3.connect

    def track_connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(card_store.sqlite3, 'connect', track_connect)
    assert CardStore(tmp_path / 'cards.sqlite3').list('owner') == []
    assert opened
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            connection.execute('SELECT 1')
