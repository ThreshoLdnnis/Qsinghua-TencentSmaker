"""Explicit server-side fixtures for browser integration, never a classifier."""
from app.schemas.psychology import PsychologyRequest
from app.psychology.mock import fixture_result
from app.schemas.understanding import ReflectionFields


class ScriptedSupportModel:
    def __init__(self, route='routine_support'):
        self.route = route

    async def generate_structured(self, *, system_prompt, request_json):
        request = PsychologyRequest.model_validate_json(request_json)
        result = fixture_result(self.route)
        result.reply = '【固定脚本演示，不进行心理判断】' + result.reply
        if self.route == 'routine_support':
            if 'REQUIRE_STRUCTURED_UNDERSTANDING: true' in system_prompt:
                result.understanding = ReflectionFields(
                    facts='【固定脚本演示】你刚才提供了一段希望被倾听的表达。',
                    interpretation='【固定脚本演示】可能希望先整理这段经历；需要你确认。',
                    emotions='【固定脚本演示】尚不确定，需要你确认此刻的感受。',
                    needs='【固定脚本演示】尚不确定，需要你确认希望怎样被支持。')
            confirmed = [r for r in request.records if r.evidence_type == 'confirmed_memory']
            observations = [r for r in request.records if r.evidence_type == 'device_observation']
            result.reply += '\n本轮输入：' + request.current_message.content[:500]
            if confirmed:
                # The input builder prioritizes current understandings, newest
                # update first; legacy confirmed drafts are appended afterwards.
                # Respect that order instead of inferring recency from source IDs.
                result.reply += '\n当前已确认内容：' + confirmed[0].content[:600]
                result.evidence_refs.append(confirmed[0].source_id)
            result.reply += f'\n本轮收到 {len(observations)} 组已授权设备观察。'
        return result.model_dump_json()
