"""Session-facing preparation; ephemeral sidecar stays outside the model request."""
from dataclasses import dataclass
import hashlib
import json
from uuid import UUID

from app.agent.errors import RuntimeFailure
from app.schemas.psychology import PsychologyRequest, SourceText, HistorySource, RecordSource
from app.schemas.session import Message, SessionStatus
from app.schemas.understanding import ReflectionFields
from app.services.state_analysis import analyze_changes, AnalysisConfig
from app.services.understanding_service import UnderstandingService
from app.services.wearable_service import WearableService


@dataclass(frozen=True)
class PreparedPsychologyRequest:
    request: PsychologyRequest
    source_manifest: dict
    wearable_revision: int
    omitted_observations: int
    omitted_understandings: int
    fingerprint: str
    memory_revision: int | None = None
    memory_enabled: bool = True


class PsychologyInputBuilder:
    def __init__(self, sessions):
        self.sessions = sessions
        self.wearables = WearableService(sessions)
        self.understandings = UnderstandingService(sessions)

    async def prepare(self, session_id: UUID, request_id: UUID, *, current_message: str,
                      history: list[Message], as_of, config: AnalysisConfig | None = None,
                      priority_metrics: tuple[str, ...] = (),
                      excluded_understanding_ids: tuple[str, ...] = ()):
        """Caller explicitly selects history; module 7 owns historical dependency filtering."""
        record = self.sessions.require(session_id)
        async with record.lock:
            return self.prepare_locked(
                session_id, request_id, current_message=current_message, history=history,
                as_of=as_of, config=config, priority_metrics=priority_metrics,
                excluded_understanding_ids=excluded_understanding_ids,
            )

    def prepare_locked(self, session_id: UUID, request_id: UUID, *, current_message: str,
                       history: list[Message], as_of, config: AnalysisConfig | None = None,
                       priority_metrics: tuple[str, ...] = (),
                       excluded_understanding_ids: tuple[str, ...] = ()):
        """Prepare synchronously while the caller holds this session's lock.

        Current-turn corrections can suppress selected confirmed interpretations without
        changing their stored state or acquiring the non-reentrant lock a second time.
        """
        record = self.sessions.require(session_id)
        if not record.lock.locked():
            raise RuntimeFailure('session_lock_required', '准备心理输入前必须持有会话锁。')
        snapshot = self.wearables.snapshot(session_id, 'model_context')
        self.wearables.validate_snapshot(session_id, snapshot)
        allowed = set().union(*(c.allowed_metrics for c in record.wearables.consents.values() if 'model_context' in c.scopes))
        analysis = analyze_changes(snapshot, as_of=as_of, config=config, authorized_metrics=allowed)
        excluded = set(excluded_understanding_ids)
        understood = [u for u in self.understandings.current(session_id, scope='model_context')
                      if u.understanding_id not in excluded]
        sources = {'current_1': {'kind': 'current_message'}}
        selected_history = []
        for index, item in enumerate(history):
            message = Message.model_validate(item.model_dump())
            identity = f'history_{index+1:04}'
            selected_history.append(HistorySource(source_id=identity, role=message.role, content=message.content))
            sources[identity] = {'kind': 'selected_history', 'selected_index': index, 'role': message.role}
        records, groups, chosen = [], set(), []
        ordered = sorted(analysis.observations, key=lambda o: (o.metric_id not in priority_metrics, not o.inquiry_candidate))
        for observation in ordered:
            if len(chosen) >= 6: break
            if observation.evidence_group not in groups and len(groups) >= 3: continue
            groups.add(observation.evidence_group)
            chosen.append(observation)
            identity = f'record_{len(records)+1:04}'
            summary = dict(metric=observation.metric_id, is_simulated=analysis.is_simulated,
                baseline_window=observation.baseline_window.model_dump(mode='json'),
                recent_window=observation.recent_window.model_dump(mode='json'),
                baseline_valid_days=observation.baseline_valid_days, recent_valid_days=observation.recent_valid_days,
                baseline=observation.baseline_median, recent=observation.recent_median,
                delta=observation.delta, unit=observation.unit, evidence_group=observation.evidence_group,
                method=observation.measurement_method, algorithm=observation.source_algorithm_version,
                limitation='Observation only; cause unknown; correlated metrics are not independent evidence.')
            records.append(RecordSource(source_id=identity, evidence_type='device_observation', content=json.dumps(summary, ensure_ascii=False)))
            sources[identity] = dict(kind='analysis', analysis_id=analysis.analysis_id,
                evidence_revision=analysis.evidence_revision, record_refs=[r.model_dump() for r in observation.record_refs])
        # An explicit deterministic cap; omitted count is visible to caller, never pretend completeness.
        for understanding in sorted(understood, key=lambda u: u.updated_at, reverse=True)[:4]:
            identity = f'record_{len(records)+1:04}'
            records.append(RecordSource(source_id=identity, evidence_type='confirmed_memory',
                content='用户确认的当前理解（非临床事实，非长期记忆）：'+(
                    understanding.fields.model_dump_json() if understanding.fields else understanding.interpretation)))
            sources[identity] = dict(kind='understanding', source_id=understanding.understanding_id, revision=understanding.revision)
        memory_revision = None
        memory_enabled = bool(getattr(record, 'recall_enabled', True))
        loader = getattr(self.sessions, 'recall_loader', None)
        if memory_enabled and callable(loader):
            try:
                memory_revision, cards = loader()
                if type(memory_revision) is not int or memory_revision < 0 or not isinstance(cards, list) or len(cards) > 1000:
                    raise ValueError('invalid recall snapshot')
                selected_ids = set()
                for card in cards:
                    if not isinstance(card, dict) or card.get('remember_for_future') is not True:
                        continue
                    card_id, revision = card.get('card_id'), card.get('revision')
                    if (not isinstance(card_id, str) or not card_id.strip() or len(card_id) > 256
                            or type(revision) is not int or revision < 1 or card_id in selected_ids):
                        raise ValueError('invalid recall identity')
                    fields = ReflectionFields.model_validate(card.get('fields'))
                    extras = {key: card.get(key, '') for key in ('keep_text', 'next_step')}
                    if any(not isinstance(value, str) or len(value) > 2000 for value in extras.values()):
                        raise ValueError('invalid recall text')
                    title = card.get('title', fields.facts[:256])
                    if not isinstance(title, str) or len(title) > 256:
                        raise ValueError('invalid recall title')
                    identity = f'record_{len(records)+1:04}'
                    records.append(RecordSource(source_id=identity, evidence_type='confirmed_memory', content=(
                        '用户明确允许在后续对话参考的经历卡；理解仍可纠正、非临床事实：'
                        + json.dumps({'fields': fields.model_dump(), **extras}, ensure_ascii=False))))
                    sources[identity] = dict(kind='experience_card', source_id=card_id, revision=revision, title=title)
                    selected_ids.add(card_id)
                    if len(selected_ids) == 3:
                        break
            except Exception:
                raise RuntimeFailure('memory_unavailable', '已授权经历卡暂不可读取，未发送不完整的记忆上下文。', 503) from None
        request = PsychologyRequest(schema_version='0.1.0', session_id=session_id, request_id=request_id,
            session_revision=record.session.revision, current_message=SourceText(source_id='current_1', content=current_message),
            history=selected_history, records=records)
        return PreparedPsychologyRequest(request, sources, snapshot.revision, len(analysis.observations)-len(chosen),
            max(0, len(understood)-4), hashlib.sha256(request.model_dump_json().encode()).hexdigest(), memory_revision, memory_enabled)

    def validate_current(self, prepared: PreparedPsychologyRequest):
        """Use before/after evaluate; module 7 must also check under its commit lock."""
        request = prepared.request
        if hashlib.sha256(request.model_dump_json().encode()).hexdigest() != prepared.fingerprint:
            raise RuntimeFailure('psychology_input_changed', '心理输入准备后被修改。')
        record = self.sessions.require(request.session_id)
        if bool(getattr(record, 'recall_enabled', True)) != prepared.memory_enabled:
            raise RuntimeFailure('stale_memory_input', '本轮后续参考选择已变化，结果不可提交。')
        if prepared.memory_revision is not None:
            current = getattr(self.sessions, 'recall_current', None)
            if not callable(current) or current(prepared.memory_revision) is not True:
                raise RuntimeFailure('stale_memory_input', '经历卡或后续参考授权已变化，本轮结果不可提交。')
        if (record.lifecycle_pending or record.session.status != SessionStatus.ACTIVE
                or record.session.revision != request.session_revision
                or record.wearables.revision != prepared.wearable_revision):
            raise RuntimeFailure('stale_psychology_input', '会话、来源或授权已变化，心理结果不可提交。')
