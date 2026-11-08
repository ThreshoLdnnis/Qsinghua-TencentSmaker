"""Product boundary tests with a deterministic transport double, not live AI proof."""
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.product.main import create_app


FIELDS = dict(facts='我在小组讨论时没有说完', interpretation='可能在意是否被认真听见', emotions='可能感到失落', needs='可能需要有空间完整表达')


class StructuredDouble:
    def __init__(self):
        self.requests = []
        self.invalid = False

    async def generate_structured(self, *, system_prompt, request_json):
        payload = json.loads(request_json)
        self.requests.append(payload)
        if self.invalid:
            return 'unparseable'
        return json.dumps(dict(route='routine_support', evidence_refs=['current_1'],
            uncertainties=['测试替身，不是真实模型结论'], reply='我先把这四点作为待你核对的理解。',
            understanding=FIELDS, suggested_next_step=None, memory_update=None, follow_up_offer=None), ensure_ascii=False)


@pytest.fixture
def product(tmp_path):
    model = StructuredDouble()
    app = create_app(Settings(_env_file=None, product_data_dir=tmp_path,
        product_origin='https://testserver', product_cookie_secure=True), model_factory=lambda: model)
    with TestClient(app, base_url='https://testserver') as client:
        yield client, model, app


def register(client, username='tester_one'):
    response = client.post('/api/account/register', json=dict(username=username, password='demo-password-123', consent=True), headers={'Origin': 'https://testserver'})
    assert response.status_code == 201, response.text
    return {'Origin': 'https://testserver', 'x-csrf-token': response.json()['csrf_token']}


def journey(client, headers, **extra):
    response = client.post('/api/support/sessions', json={}, headers=headers)
    assert response.status_code == 201, response.text
    sid = response.json()['session_id']
    response = client.post(f'/api/support/sessions/{sid}/messages', json=dict(content='小组讨论让我难过', request_id=str(uuid4()), model_consent=True, **extra), headers=headers)
    assert response.status_code == 200, response.text
    return sid, response.json()


def confirm(client, headers, sid, view):
    value = view['understanding']
    # Real UI saves corrected fields, then confirms the newly issued revision/token.
    corrected = {**FIELDS, 'emotions': '我其实感到生气，而不是失落'}
    response = client.put(f"/api/support/sessions/{sid}/understandings/{value['understanding_id']}",
        headers=headers, json=dict(operation_id=str(uuid4()), expected_revision=value['revision'],
            interpretation=corrected['interpretation'], fields=corrected, origin='user_report', evidence_refs=value['evidence_refs']))
    assert response.status_code == 200, response.text
    edited = response.json()
    response = client.post(f"/api/support/sessions/{sid}/understandings/{value['understanding_id']}/confirm",
        headers=headers, json=dict(operation_id=str(uuid4()), expected_revision=edited['understanding']['revision'], confirmation_token=edited['confirmation_token']))
    assert response.status_code == 200, response.text
    return response.json()['understanding']


def save(client, headers, sid, understood):
    body = dict(operation_id=str(uuid4()), session_id=sid, understanding_id=understood['understanding_id'],
        expected_revision=understood['revision'], choice='next', keep_text='保留表达自己的勇气',
        release_text='绝不应被记住的放下文字', next_step='明天请同学给我一分钟说完', remember_for_future=True)
    response = client.post('/api/product/cards', headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def test_correction_confirm_card_recall_and_withdrawal(product):
    client, model, _ = product
    headers = register(client)
    cookie = client.cookies.get('lingyv_session')
    sid, response = journey(client, headers)
    view = response['generated_understanding']
    unconfirmed = view['understanding']
    refused = client.post('/api/product/cards', headers=headers, json=dict(operation_id=str(uuid4()), session_id=sid,
        understanding_id=unconfirmed['understanding_id'], expected_revision=unconfirmed['revision'], choice='keep'))
    assert refused.status_code == 409
    understood = confirm(client, headers, sid, view)
    card, body = save(client, headers, sid, understood)
    assert card['fields']['emotions'] == '我其实感到生气，而不是失落'
    assert card['release_text'] == ''
    assert client.post('/api/product/cards', headers=headers, json=body).json()['card_id'] == card['card_id']
    sid2, reply = journey(client, headers, use_memories=True)
    assert reply['memory_refs'][0]['card_id'] == card['card_id']
    memory = json.dumps(model.requests[-1]['records'], ensure_ascii=False)
    assert '生气' in memory and '绝不应被记住' not in memory
    # A second browser/account cannot list, read or modify the first owner's records.
    client.cookies.clear()
    other = register(client, 'tester_two')
    assert client.get('/api/product/cards').json() == []
    assert client.get(f'/api/support/sessions/{sid}').status_code == 404
    assert client.delete(f"/api/product/cards/{card['card_id']}?expected_revision=1", headers=other).status_code == 404
    client.cookies.set('lingyv_session', cookie)
    assert client.get('/api/product/cards').json()[0]['card_id'] == card['card_id']
    removed = client.delete(f"/api/product/cards/{card['card_id']}?expected_revision=1", headers=headers)
    assert removed.status_code == 204
    assert client.get(f'/api/support/sessions/{sid2}').json()['messages'] == []
    assert client.post('/api/product/cards', headers=headers, json=body).status_code == 409
    _, reply = journey(client, headers, use_memories=True)
    assert reply['memory_refs'] == []


def test_auth_csrf_consent_and_failures_do_not_commit(product):
    client, model, _ = product
    assert client.post('/api/support/sessions', json={}).status_code == 401
    headers = register(client)
    assert client.post('/api/support/sessions', json={}, headers={'Origin':'https://hostile.test'}).status_code == 403
    assert client.post('/api/support/sessions', json={}, headers={'Origin':'https://testserver'}).status_code == 403
    sid = client.post('/api/support/sessions', json={}, headers=headers).json()['session_id']
    response = client.post(f'/api/support/sessions/{sid}/messages', headers=headers, json=dict(content='hello',request_id=str(uuid4())))
    assert response.status_code == 422 and not model.requests
    model.invalid = True
    response = client.post(f'/api/support/sessions/{sid}/messages', headers=headers, json=dict(content='hello',request_id=str(uuid4()),model_consent=True))
    assert response.status_code >= 400
    assert client.get(f'/api/support/sessions/{sid}').json()['messages'] == []
    assert client.post('/api/account/login', headers={'Origin':'https://testserver'}, json={'username':'x','password':'SECRET-MUST-NOT-ECHO','consent':False}).text.find('SECRET-MUST-NOT-ECHO') == -1
    assert client.post('/api/account/logout', headers=headers).status_code == 200
    assert client.get('/api/account/me').json() == {'user':None}
    assert client.get('/api/product/cards').status_code == 401
    assert client.get('/archives').status_code == 404


def test_cards_survive_app_restart_without_persisting_conversations(tmp_path):
    config = Settings(_env_file=None, product_data_dir=tmp_path, product_origin='https://testserver')
    with TestClient(create_app(config, model_factory=StructuredDouble), base_url='https://testserver') as client:
        headers = register(client)
        sid, reply = journey(client, headers)
        card, _ = save(client, headers, sid, confirm(client, headers, sid, reply['generated_understanding']))
    with TestClient(create_app(config, model_factory=StructuredDouble), base_url='https://testserver') as client:
        response = client.post('/api/account/login', json=dict(username='tester_one', password='demo-password-123', consent=True), headers={'Origin':'https://testserver'})
        headers = {'Origin':'https://testserver','x-csrf-token':response.json()['csrf_token']}
        assert client.get('/api/product/cards').json()[0]['card_id'] == card['card_id']
        assert client.get(f'/api/support/sessions/{sid}').status_code == 404
        _, reply = journey(client, headers, use_memories=True)
        assert reply['memory_refs'][0]['card_id'] == card['card_id']
