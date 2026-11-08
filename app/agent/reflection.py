"""Prepare a proposed canvas without mutating state or reacquiring the session lock."""
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.agent.errors import RuntimeFailure
from app.schemas.understanding import Understanding
from app.schemas.understanding_service import UnderstandingView
from app.schemas.wearable import EvidenceReference
from app.services.understanding_service import UnderstandingService
from app.services.understanding_state import UnderstandingEntry, UserReport


@dataclass(frozen=True)
class GeneratedUnderstanding:
    reports: tuple[UserReport, ...]
    entry: UnderstandingEntry

    def view(self):
        return UnderstandingView(understanding=self.entry.value.model_copy(deep=True), confirmation_token=self.entry.token)


def prepare_generated_understanding(record, sessions, prepared, result, dependencies, settings):
    """Model fields are hypotheses; source identities and confirmation token are server-owned.

    Input reports are split into bounded exact chunks, never truncated. Device-derived
    hypotheses conservatively depend on all current model-context consents. Card recall
    has its own epoch guard and is invalidated by the owning product service.
    """
    if result.understanding is None:
        return None
    if not record.lock.locked():
        raise RuntimeFailure('session_lock_required', '生成理解前必须持有会话锁。')
    fields = result.understanding.model_copy(deep=True)
    reports, refs = [], []

    def reported_text(text):
        for start in range(0, len(text), 2000):
            report = UserReport(str(uuid4()), text[start:start+2000])
            reports.append(report)
            refs.append(EvidenceReference(kind='user_report', source_id=report.report_id, revision=1))

    reported_text(prepared.request.current_message.content)
    history = {source.source_id: source for source in prepared.request.history}
    for source_id in result.evidence_refs:
        metadata = prepared.source_manifest[source_id]
        if metadata['kind'] == 'selected_history' and history[source_id].role == 'user':
            reported_text(history[source_id].content)
        if metadata['kind'] == 'draft':
            raise RuntimeFailure('invalid_understanding_source', '通用草稿不能充当本轮理解的个人事实来源。', 502)
    refs.extend(ref.model_copy(deep=True) for ref in dependencies.understanding_refs)
    wearable = dependencies.wearable_revision is not None
    if wearable:
        refs.extend(EvidenceReference(kind='consent', source_id=str(consent.consent_id), revision=consent.revision)
                    for consent in record.wearables.consents.values() if 'model_context' in consent.scopes)
    refs = list({(ref.kind, ref.source_id, ref.revision): ref for ref in refs}.values())
    if len(refs) > 200:
        raise RuntimeFailure('understanding_sources_exceeded', '本轮理解来源超出预算，未提交。', 413)
    staged_ids = {report.report_id for report in reports}
    external = [ref for ref in refs if ref.source_id not in staged_ids]
    checked_wearable = UnderstandingService(sessions, settings)._check_refs(record, external, scope='model_context')
    if checked_wearable != wearable:
        raise RuntimeFailure('source_invalid', '本轮理解的设备来源授权已失效。')
    now = datetime.now(timezone.utc)
    value = Understanding(understanding_id=str(uuid4()), revision=1, status='proposed',
        interpretation=fields.interpretation or next(text for text in (fields.facts, fields.emotions, fields.needs) if text),
        fields=fields, origin='agent_hypothesis', evidence_refs=refs,
        created_at=now, updated_at=now)
    if len(value.model_dump_json()) > settings.runtime_max_context_chars:
        raise RuntimeFailure('understanding_too_large', '理解超过上下文预算。', 413)
    return GeneratedUnderstanding(tuple(reports), UnderstandingEntry(value, uuid4(),
        record.wearables.revision if wearable else None, 'model_context'))


def commit_generated_understanding(record, candidate):
    if candidate is not None:
        record.understandings.reports.update({report.report_id: report for report in candidate.reports})
        record.understandings.entries[candidate.entry.value.understanding_id] = candidate.entry
