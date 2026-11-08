"""Fictional inputs and injected models; no external model calls."""
import asyncio
import json
from uuid import uuid4

import pytest

from app.agent.errors import RuntimeFailure
from app.agent.orchestrator import AgentOrchestrator
from app.config.settings import Settings
from app.psychology.inputs import PsychologyInputBuilder
from app.psychology.mock import fixture_result
from app.schemas.archive import SaveArchiveRequest
from app.schemas.message import SendMessageRequest
from app.schemas.understanding import ReflectionFields
from app.schemas.understanding_service import ConfirmUnderstanding, EditUnderstanding
from app.services.archive_service import ArchiveService
from app.services.archive_store import SQLiteArchiveStore
from app.services.session_service import SessionService
from app.services.understanding_service import UnderstandingService


FIELDS = dict(facts='用户说最近旅行后作息变晚。', interpretation='可能是行程变化，需要你确认。',
              emotions='可能有些疲惫，需要你确认。', needs='也许希望恢复自己的节奏，需要你确认。')


class Model:
    def __init__(self, *, fields=FIELDS, route='routine_support', refs=None):
        self.fields, self.route, self.refs = fields, route, refs
        self.requests, self.prompts = [], []

    async def generate_structured(self, *, system_prompt, request_json):
        self.requests.append(json.loads(request_json)); self.prompts.append(system_prompt)
        payload = fixture_result(self.route).model_dump()
        payload['understanding'] = self.fields
        if self.refs is not None:
            payload['evidence_refs'] = self.refs
        return json.dumps(payload, ensure_ascii=False)


def setup(*, strict=True):
    sessions = SessionService(); sid = sessions.create().session_id
    settings = Settings(psychology_enabled=True, psychology_require_understanding=strict)
    return sessions, sid, AgentOrchestrator(sessions, settings)


def test_structured_call_commits_report_canvas_and_messages_atomically_and_replays():
    async def run():
        sessions, sid, agent = setup(); model = Model()
        request = SendMessageRequest(content='虚构：旅行之后作息变晚了')
        response = await agent.handle_message(sid, request, model)
        generated = response.generated_understanding
        assert generated.understanding.fields == ReflectionFields(**FIELDS)
        assert generated.understanding.status == 'proposed' and generated.understanding.revision == 1
        assert generated.confirmation_token is not None
        assert generated.understanding.origin == 'agent_hypothesis'
        assert len(sessions.get(sid).messages) == 2
        record = sessions.require(sid)
        assert [r.content for r in record.understandings.reports.values()] == [request.content]
        assert len(record.understandings.entries) == 1
        assert 'REQUIRE_STRUCTURED_UNDERSTANDING: true' in model.prompts[0]
        assert '不是已经确认的事实或诊断' in model.prompts[0]
        assert await agent.handle_message(sid, request, model) == response
        assert len(model.requests) == len(record.understandings.entries) == 1
    asyncio.run(run())


@pytest.mark.parametrize('fields,code', [
    (None, 'understanding_required'),
    ({key: ' ' for key in FIELDS}, 'output_validation_failed'),
    ({key: value for key, value in FIELDS.items() if key != 'needs'}, 'output_validation_failed'),
    ({**FIELDS, 'diagnosis': 'not allowed'}, 'output_validation_failed'),
])
def test_invalid_or_missing_understanding_fails_without_partial_commit(fields, code):
    async def run():
        sessions, sid, agent = setup(); model = Model(fields=fields)
        request = SendMessageRequest(content='虚构输入')
        with pytest.raises(RuntimeFailure) as error:
            await agent.handle_message(sid, request, model)
        assert error.value.code == code
        assert not sessions.get(sid).messages
        assert not sessions.require(sid).understandings.entries
        assert not sessions.require(sid).understandings.reports
        with pytest.raises(RuntimeFailure):
            await agent.handle_message(sid, request, model)
        assert len(model.requests) == 1
    asyncio.run(run())


@pytest.mark.parametrize('strict,route', [(False, 'routine_support'), (True, 'urgent_real_world_help')])
def test_legacy_and_direct_safety_response_do_not_require_canvas(strict, route):
    async def run():
        sessions, sid, agent = setup(strict=strict)
        response = await agent.handle_message(sid, SendMessageRequest(content='虚构：需要支持'), Model(fields=None, route=route))
        assert response.generated_understanding is None
        assert response.psychology.result.route == route
        assert len(sessions.get(sid).messages) == 2
    asyncio.run(run())


def test_canvas_requires_current_input_source_and_keeps_completed_history_on_failure():
    async def run():
        sessions, sid, agent = setup(); model = Model()
        await agent.handle_message(sid, SendMessageRequest(content='虚构：第一轮'), model)
        before = sessions.get(sid).messages
        with pytest.raises(RuntimeFailure) as error:
            await agent.handle_message(sid, SendMessageRequest(content='虚构：第二轮'), Model(refs=['history_0001']))
        assert error.value.code == 'invalid_understanding_source'
        assert sessions.get(sid).messages == before
        assert len(sessions.require(sid).understandings.entries) == 1
    asyncio.run(run())


def test_fields_edit_invalidates_old_confirmation_and_reply_replay_and_informs_next_call():
    async def run():
        sessions, sid, agent = setup(); model = Model(); service = UnderstandingService(sessions)
        request = SendMessageRequest(content='虚构：旅行')
        original = (await agent.handle_message(sid, request, model)).generated_understanding
        changed_fields = ReflectionFields(**{**FIELDS, 'emotions': '用户纠正：其实是兴奋。', 'needs': '用户希望保留旅行的好奇心。'})
        edited = await service.edit(sid, original.understanding.understanding_id, EditUnderstanding(
            expected_revision=1, interpretation=original.understanding.interpretation, fields=changed_fields,
            origin='user_report', evidence_refs=original.understanding.evidence_refs))
        with pytest.raises(RuntimeFailure) as error:
            await service.confirm(sid, original.understanding.understanding_id, ConfirmUnderstanding(
                expected_revision=1, confirmation_token=original.confirmation_token))
        assert error.value.code == 'stale_revision'
        confirmed = await service.confirm(sid, original.understanding.understanding_id, ConfirmUnderstanding(
            expected_revision=edited.understanding.revision, confirmation_token=edited.confirmation_token))
        assert confirmed.understanding.confirmed_revision == confirmed.understanding.revision == 3
        assert confirmed.confirmation_token is None
        with pytest.raises(RuntimeFailure) as error:
            await agent.handle_message(sid, request, model)
        assert error.value.code == 'source_withdrawn'
        await agent.handle_message(sid, SendMessageRequest(content='虚构：接着聊'), model)
        assert any('用户纠正：其实是兴奋' in r['content'] for r in model.requests[-1]['records'])
        assert any('用户希望保留旅行的好奇心' in r['content'] for r in model.requests[-1]['records'])
        assert all(item['role'] == 'user' for item in model.requests[-1]['history'])
    asyncio.run(run())


def test_field_only_correction_interrupts_running_call_and_discards_late_canvas():
    async def run():
        sessions, sid, agent = setup(); service = UnderstandingService(sessions)
        original = (await agent.handle_message(sid, SendMessageRequest(content='虚构：旅行'), Model())).generated_understanding
        entered = asyncio.Event()
        class Delayed(Model):
            async def generate_structured(self, **kwargs):
                entered.set()
                await asyncio.Event().wait()
        task = asyncio.create_task(agent.handle_message(sid, SendMessageRequest(content='虚构：继续'), Delayed()))
        await entered.wait()
        edited = await service.edit(sid, original.understanding.understanding_id, EditUnderstanding(
            expected_revision=1, interpretation=original.understanding.interpretation,
            fields=ReflectionFields(**{**FIELDS, 'needs': '希望安静休息。'}),
            origin=original.understanding.origin, evidence_refs=original.understanding.evidence_refs))
        outcome = await asyncio.gather(task, return_exceptions=True)
        assert isinstance(outcome[0], RuntimeFailure) and outcome[0].code == 'run_cancelled'
        assert edited.understanding.fields.needs == '希望安静休息。'
        assert len(sessions.get(sid).messages) == 2
        assert len(sessions.require(sid).understandings.entries) == 1
    asyncio.run(run())


def cards(count=4):
    return [dict(card_id=f'card-{i}', revision=i+1, fields=FIELDS,
                 keep_text='可以保留的好奇心', next_step='今天早点休息', release_text='PRIVATE RELEASE NEVER SEND',
                 remember_for_future=True) for i in range(count)]


def test_recall_is_capped_explicit_sanitized_and_has_manifest_identity():
    async def run():
        sessions, sid, agent = setup(); model = Model()
        sessions.recall_loader = lambda: (7, [dict(cards(1)[0], remember_for_future=False), *cards()])
        sessions.recall_current = lambda epoch: epoch == 7
        response = await agent.handle_message(sid, SendMessageRequest(content='虚构：再聊聊'), model)
        records = model.requests[0]['records']
        assert len(records) == 3
        assert 'PRIVATE RELEASE NEVER SEND' not in json.dumps(model.requests)
        assert all('release_text' not in r['content'] and 'card_id' not in r['content'] for r in records)
        refs = [s for s in response.context_manifest.sources if s.experience_card_id]
        assert [s.experience_card_id for s in refs] == ['card-0', 'card-1', 'card-2']
        assert [s.experience_card_revision for s in refs] == [1, 2, 3]
        assert refs[0].experience_card_title == FIELDS['facts']
    asyncio.run(run())


def test_turn_can_disable_recall_without_calling_loader():
    async def run():
        sessions, sid, agent = setup(); model = Model()
        sessions.require(sid).recall_enabled = False
        def forbidden():
            raise AssertionError('disabled recall must not read storage')
        sessions.recall_loader = forbidden
        await agent.handle_message(sid, SendMessageRequest(content='虚构输入'), model)
        assert not model.requests[0]['records']
    asyncio.run(run())


@pytest.mark.parametrize('change_choice', [False, True])
def test_memory_revocation_or_choice_change_during_model_call_blocks_commit(change_choice):
    async def run():
        sessions, sid, agent = setup(); epoch = [1]
        sessions.recall_loader = lambda: (epoch[0], cards(1))
        sessions.recall_current = lambda expected: epoch[0] == expected
        class Changed(Model):
            async def generate_structured(self, **kwargs):
                result = await super().generate_structured(**kwargs)
                if change_choice:
                    sessions.require(sid).recall_enabled = False
                else:
                    epoch[0] += 1
                return result
        with pytest.raises(RuntimeFailure) as error:
            await agent.handle_message(sid, SendMessageRequest(content='虚构输入'), Changed())
        assert error.value.code == 'stale_memory_input'
        assert not sessions.get(sid).messages
        assert not sessions.require(sid).understandings.entries
    asyncio.run(run())


def test_generated_fields_survive_explicit_archive_without_restoring_old_token(tmp_path):
    async def run():
        sessions, sid, agent = setup()
        view = (await agent.handle_message(sid, SendMessageRequest(content='虚构旅行'), Model())).generated_understanding
        store = SQLiteArchiveStore(tmp_path/'reflections.sqlite3')
        archives = ArchiveService(sessions, store)
        await archives.save(sid, SaveArchiveRequest(expected_revision=sessions.get(sid).revision, save_business_data=True))
        restored = SessionService()
        await ArchiveService(restored, store).restore(sid)
        current = UnderstandingService(restored).get(sid, view.understanding.understanding_id)
        assert current.understanding.fields == view.understanding.fields
        assert current.confirmation_token != view.confirmation_token
        assert restored.require(sid).understandings.entries[view.understanding.understanding_id].evidence_scope == 'model_context'
    asyncio.run(run())


def test_long_user_report_is_preserved_exactly_without_oversized_report_rows():
    async def run():
        sessions, sid, agent = setup(); text = '虚构内容' * 600
        await agent.handle_message(sid, SendMessageRequest(content=text), Model())
        reports = list(sessions.require(sid).understandings.reports.values())
        assert ''.join(report.content for report in reports) == text
        assert all(0 < len(report.content) <= 2000 for report in reports)
    asyncio.run(run())


def test_individual_unknown_fields_may_be_empty_but_all_four_keys_are_required():
    async def run():
        sessions, sid, agent = setup()
        fields = dict(facts='用户报告一次旅行。', interpretation='', emotions='', needs='')
        response = await agent.handle_message(sid, SendMessageRequest(content='虚构旅行'), Model(fields=fields))
        assert response.generated_understanding.understanding.fields.model_dump() == fields
        assert response.generated_understanding.understanding.interpretation == fields['facts']
    asyncio.run(run())


def test_generated_device_hypothesis_keeps_model_context_scope_for_edit_confirm_and_revoke():
    async def run():
        from datetime import datetime, timezone
        from app.schemas.wearable_service import SetWearableConsent
        from app.services.support_views import SupportViewService
        from app.services.wearable_service import WearableService
        from app.wearables.base import MockQuery
        from app.wearables.metric_registry import METRIC_REGISTRY
        from app.wearables.mock import MockWearableAdapter
        sessions, sid, agent = setup(); data = WearableService(sessions)
        await MockWearableAdapter().import_into(data, sid, MockQuery(as_of=datetime.now(timezone.utc), scenario_id='S02'),
            expected_revision=0, operation_id=uuid4())
        await data.set_consent(sid, SetWearableConsent(expected_revision=1, provider='mock',
            allowed_metrics=list(METRIC_REGISTRY), scopes=['model_context']))
        view = (await agent.handle_message(sid, SendMessageRequest(content='虚构：看看我的近况'), Model())).generated_understanding
        entry = sessions.require(sid).understandings.entries[view.understanding.understanding_id]
        assert entry.evidence_scope == 'model_context' and entry.wearable_revision == 2
        assert SupportViewService(sessions).controls(sid)[0].understanding == view.understanding
        service = UnderstandingService(sessions)
        edited = await service.edit(sid, view.understanding.understanding_id, EditUnderstanding(
            expected_revision=1, interpretation=view.understanding.interpretation,
            fields=ReflectionFields(**{**FIELDS, 'needs': '用户希望自行安排休息。'}), origin='user_report',
            evidence_refs=view.understanding.evidence_refs))
        request = ConfirmUnderstanding(expected_revision=2, confirmation_token=edited.confirmation_token)
        confirmed = await service.confirm(sid, view.understanding.understanding_id, request)
        assert await service.confirm(sid, view.understanding.understanding_id, request) == confirmed
        assert service.current(sid, scope='model_context')
        assert not service.current(sid, scope='local_analysis')  # Confirmation grants no additional purpose.
        await data.set_consent(sid, SetWearableConsent(expected_revision=2, provider='mock', allowed_metrics=[], scopes=[]))
        assert not service.current(sid, scope='model_context')
        assert service.get(sid, view.understanding.understanding_id).understanding.status == 'invalidated'
    asyncio.run(run())
