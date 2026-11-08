"""Two real supplier calls with fictional input; no credentials/content in stdout.

python -m scripts.verify_live_product --live
Uses a disposable temporary account/database, never the user's saved records.
"""
import argparse
import json
import secrets
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi.testclient import TestClient
from app.config.settings import get_settings
from app.product.main import create_app


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True)
    parser.parse_args()
    settings = get_settings()
    if not settings.key_configured:
        print(json.dumps({'status': 'not_run', 'reason': 'model_not_configured'}))
        return 2
    with TemporaryDirectory(prefix='lingyv-live-probe-') as folder:
        config = settings.model_copy(update={'product_data_dir': Path(folder), 'product_origin': 'https://probe.local',
            'product_cookie_secure': True, 'llm_max_tokens': max(1800, settings.llm_max_tokens)})
        with TestClient(create_app(config), base_url='https://probe.local') as client:
            def success(response, expected=200):
                if response.status_code != expected:
                    try: code = response.json().get('detail', {}).get('code', 'unexpected_response')
                    except Exception: code = 'unexpected_response'
                    raise RuntimeError(f'probe_failed:{response.status_code}:{code}')
                return response.json() if response.content else None

            registered = success(client.post('/api/account/register', headers={'Origin': 'https://probe.local'},
                json={'username': 'probe_'+secrets.token_hex(5), 'password': secrets.token_urlsafe(24), 'consent': True}), 201)
            headers = {'Origin': 'https://probe.local', 'x-csrf-token': registered['csrf_token']}
            sid = success(client.post('/api/support/sessions', json={}, headers=headers), 201)['session_id']
            turn = success(client.post(f'/api/support/sessions/{sid}/messages', headers=headers, json={
                'content': '这是虚构的软件验收案例：今天的小组讨论里我没能把想法说完，感到失落。我希望下次有空间表达。请先把理解当作待我确认的假设。',
                'request_id': str(uuid4()), 'model_consent': True, 'use_memories': False}))
            proposed = turn['generated_understanding']
            if proposed is None:
                raise RuntimeError('probe_failed:no_structured_understanding')
            value = proposed['understanding']
            fields = {**value['fields'], 'emotions': '我纠正一下：比起失落，我其实更生气，因为话被打断。'}
            edited = success(client.put(f"/api/support/sessions/{sid}/understandings/{value['understanding_id']}", headers=headers,
                json={'operation_id': str(uuid4()), 'expected_revision': value['revision'], 'interpretation': fields['interpretation'] or fields['emotions'],
                      'fields': fields, 'origin': 'user_report', 'evidence_refs': value['evidence_refs']}))
            confirmed = success(client.post(f"/api/support/sessions/{sid}/understandings/{value['understanding_id']}/confirm", headers=headers,
                json={'operation_id': str(uuid4()), 'expected_revision': edited['understanding']['revision'], 'confirmation_token': edited['confirmation_token']}))['understanding']
            card = success(client.post('/api/product/cards', headers=headers, json={
                'operation_id': str(uuid4()), 'session_id': sid, 'understanding_id': confirmed['understanding_id'],
                'expected_revision': confirmed['revision'], 'choice': 'next', 'keep_text': '我愿意表达的勇气',
                'release_text': '', 'next_step': '下次先请求一分钟表达', 'remember_for_future': True}), 201)
            new_sid = success(client.post('/api/support/sessions', headers=headers, json={}), 201)['session_id']
            again = success(client.post(f'/api/support/sessions/{new_sid}/messages', headers=headers, json={
                'content': '继续这个虚构案例：明天还有小组讨论。请结合我允许参考的经历卡，先核对我之前纠正的感受，再提出一个可以选择的小行动。',
                'request_id': str(uuid4()), 'model_consent': True, 'use_memories': True}))
            if not any(item['card_id'] == card['card_id'] for item in again['memory_refs']):
                raise RuntimeError('probe_failed:recall_missing')
            success(client.delete(f"/api/product/cards/{card['card_id']}?expected_revision=1", headers=headers), 204)
            print(json.dumps({'status': 'passed', 'supplier_calls': 2, 'structured_understanding': True,
                              'user_correction_confirmed': True, 'owned_card_saved': True, 'next_conversation_memory_sent': True,
                              'withdrawn_card_removed': not success(client.get('/api/product/cards'))}))
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
