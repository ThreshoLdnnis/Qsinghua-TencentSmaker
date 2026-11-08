"""Public product boundary. The original app.main remains a local engineering API.

Run ONE worker: active journeys are process-local; only explicitly saved cards persist.
Never expose app.main on the public proxy, and never use client-supplied owner IDs.
"""
import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import asdict
import secrets
from time import monotonic
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field

from app.agent.errors import RuntimeFailure
from app.agent.orchestrator import AgentOrchestrator
from app.api_support import make_support_router
from app.calls.scheduler import CallScheduler
from app.config.settings import Settings, get_settings
from app.llm.client import DeepSeekClient
from app.llm.errors import LLMError
from app.product.auth_store import AuthStore
from app.product.card_store import CardStore
from app.psychology.prompts import PROMPT_VERSION
from app.schemas.message import SendMessageRequest
from app.schemas.workflow import CancelWorkflowRequest
from app.services.session_service import SessionService


class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Credentials(StrictBody):
    username: str = Field(max_length=128)
    password: str = Field(max_length=256)
    consent: Literal[True]


class ProductMessage(SendMessageRequest):
    model_consent: Literal[True]
    use_memories: bool = False


class SaveCard(StrictBody):
    operation_id: UUID
    session_id: UUID
    understanding_id: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=1)
    choice: Literal['keep', 'release', 'next']
    keep_text: str = Field(default='', max_length=2000)
    release_text: str = Field(default='', max_length=2000)
    next_step: str = Field(default='', max_length=2000)
    remember_for_future: bool = False


class ChangeCard(StrictBody):
    expected_revision: int = Field(ge=1)
    remember_for_future: bool


class WindowLimit:
    def __init__(self):
        self.windows = defaultdict(deque)

    def check(self, key, maximum, seconds):
        now = monotonic()
        queue = self.windows[key]
        while queue and queue[0] <= now-seconds:
            queue.popleft()
        if len(queue) >= maximum:
            raise RuntimeFailure('rate_limited', '请求过于频繁，请稍后再试。', 429)
        queue.append(now)
        if len(self.windows) > 10000:
            for old in [k for k, v in self.windows.items() if not v or v[-1] < now-86400]:
                del self.windows[old]


class OwnedSessions(SessionService):
    """Freeze the old service before account lifecycle awaits can yield control."""
    closed = False

    def check_open(self):
        if self.closed:
            raise RuntimeFailure('authentication_required', '账号会话已退出，请重新登录。', 401)

    def create(self):
        self.check_open()
        return super().create()

    def require(self, session_id):
        self.check_open()
        return super().require(session_id)


def create_app(config: Settings | None = None, model_factory=None):
    settings = (config or get_settings()).model_copy(update={
        'psychology_enabled': True, 'psychology_demo_mode': False,
        'psychology_require_understanding': True,
    })
    if settings.product_cookie_secure and not settings.product_origin.startswith('https://'):
        raise ValueError('Secure product cookies require an HTTPS PRODUCT_ORIGIN. For local development explicitly set PRODUCT_COOKIE_SECURE=false.')
    auth = AuthStore(settings.product_data_dir / 'accounts.sqlite3')
    cards = CardStore(settings.product_data_dir / 'cards.sqlite3')
    owners: dict[str, SessionService] = {}
    current: ContextVar[SessionService] = ContextVar('product_sessions')
    limits = WindowLimit()
    blocked_owners = set()
    retiring_owners = set()

    @asynccontextmanager
    async def lifespan(app):
        app.state.scheduler = CallScheduler(settings)
        try:
            yield
        finally:
            await app.state.scheduler.close()

    app = FastAPI(title='Lingyv product API', version='0.8.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.auth_store, app.state.card_store = auth, cards
    app.state.product_settings = settings

    async def error_response(error):
        payload = {'detail': {'code': error.code, 'message': error.message}}
        notice = getattr(error, 'support_notice', None)
        if notice:
            payload['support_notice'] = notice if isinstance(notice, dict) else asdict(notice)
        return JSONResponse(payload, status_code=error.status_code)

    @app.exception_handler(RuntimeFailure)
    @app.exception_handler(LLMError)
    async def handle_error(request, error):
        return await error_response(error)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, error):
        return JSONResponse({'detail': {'code': 'invalid_input', 'message': '请检查输入内容和必要授权。'}}, status_code=422)

    def owner_sessions(owner):
        if owner not in owners:
            store = OwnedSessions()
            store.recall_loader = lambda: cards.recall(owner)
            store.recall_current = lambda epoch: cards.recall(owner)[0] == epoch
            owners[owner] = store
        return owners[owner]

    async def forget_active(owner):
        store = owners.get(owner)
        if store:
            orchestrator = AgentOrchestrator(store, settings)
            await asyncio.gather(*(orchestrator.clear_history(s.session_id) for s in store.list()))

    async def close_owner(owner):
        blocked_owners.add(owner)
        store = owners.get(owner)
        if store:
            store.closed = True
            records = list(store._records.values())
            for record in records:
                record.lifecycle_pending += 1
                from app.schemas.workflow import StopReason
                AgentOrchestrator._signal(record, StopReason.SESSION_ENDED)
            # Wait for all admitted saves/model commits before deleting durable data.
            for record in records:
                async with record.lock:
                    record.session.messages.clear()
                    record.understandings.clear()
                    record.operations.clear()

    @app.middleware('http')
    async def boundary(request: Request, call_next):
        path = request.url.path
        public = path in ('/api/account/me', '/api/account/login', '/api/account/register',
                          '/api/support/health', '/api/support/support', '/api/support/wearables/catalog')
        token = None
        try:
            if request.headers.get('content-length', '').isdigit() and int(request.headers['content-length']) > 4*1024*1024:
                raise RuntimeFailure('request_too_large', '请求过大。', 413)
            principal = None
            raw = request.cookies.get('lingyv_session', '')
            if raw:
                try:
                    principal = await asyncio.to_thread(auth.authenticate, raw)
                except RuntimeFailure as error:
                    if error.code != 'authentication_required':
                        raise
            if not public and path.startswith('/api/') and not principal:
                raise RuntimeFailure('authentication_required', '请先登录。', 401)
            if principal and principal['user']['id'] in blocked_owners:
                if public:
                    principal = None
                else:
                    raise RuntimeFailure('authentication_required', '账号会话已退出，请重新登录。', 401)
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                if request.headers.get('origin') != settings.product_origin:
                    raise RuntimeFailure('origin_invalid', '请求来源不受信任。', 403)
                if path not in ('/api/account/login', '/api/account/register'):
                    if not principal or not secrets.compare_digest(request.headers.get('x-csrf-token', ''), principal['csrf_token']):
                        raise RuntimeFailure('csrf_invalid', '会话验证已过期，请刷新后重试。', 403)
            if principal:
                request.state.principal = principal
                request.state.owner = principal['user']['id']
                token = current.set(owner_sessions(request.state.owner))
            response = await call_next(request)
        except (RuntimeFailure, LLMError) as error:
            response = await error_response(error)
        finally:
            if token is not None:
                current.reset(token)
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                                 'Referrer-Policy': 'same-origin'})
        return response

    @app.get('/api/account/me')
    async def me(request: Request):
        return getattr(request.state, 'principal', {'user': None})

    def auth_limit(request):
        limits.check(('auth', request.client.host if request.client else 'unknown'), 12, 900)

    async def issue(user, response):
        if user['id'] in retiring_owners:
            raise RuntimeFailure('authentication_required', '账号正在删除，无法重新登录。', 401)
        raw, csrf = await asyncio.to_thread(auth.create_session, user['id'])
        if user['id'] in retiring_owners:
            await asyncio.to_thread(auth.logout, raw)
            raise RuntimeFailure('authentication_required', '账号正在删除，无法重新登录。', 401)
        blocked_owners.discard(user['id'])
        response.set_cookie('lingyv_session', raw, httponly=True, secure=settings.product_cookie_secure,
                            samesite='lax', max_age=7*86400, path='/')
        return {'user': user, 'csrf_token': csrf}

    @app.post('/api/account/register', status_code=201)
    async def register(body: Credentials, request: Request, response: Response):
        auth_limit(request)
        user = await asyncio.to_thread(auth.register, body.username, body.password)
        return await issue(user, response)

    @app.post('/api/account/login')
    async def login(body: Credentials, request: Request, response: Response):
        auth_limit(request)
        user = await asyncio.to_thread(auth.login, body.username, body.password)
        return await issue(user, response)

    @app.post('/api/account/logout')
    async def logout(request: Request, response: Response):
        await asyncio.to_thread(auth.logout, request.cookies.get('lingyv_session', ''))
        await close_owner(request.state.owner)
        owners.pop(request.state.owner, None)
        response.delete_cookie('lingyv_session', path='/', secure=settings.product_cookie_secure, httponly=True, samesite='lax')
        return {'user': None}

    @app.delete('/api/account/me', status_code=204)
    async def delete_account(request: Request, response: Response):
        owner = request.state.owner
        retiring_owners.add(owner)
        await close_owner(owner)
        await asyncio.to_thread(cards.delete_owner, owner)
        await asyncio.to_thread(auth.delete_user, owner)
        owners.pop(owner, None)
        response.delete_cookie('lingyv_session', path='/')

    def current_store():
        store = current.get()
        store.check_open()
        return store

    support_router = make_support_router(current_store)
    # Public users cannot manufacture an agent-origin hypothesis or import raw devices.
    # The confirmation/edit paths and mock trends are reused, engineering archives are absent.
    support_router.routes[:] = [r for r in support_router.routes if not
        (r.path.endswith('/wearables/import') or r.path.endswith('/wearables/delete'))]
    app.include_router(support_router, prefix='/api/support')

    @app.get('/api/support/health')
    async def health():
        return {'status': 'ok', 'service': 'Lingyv product',
                'llm': {'provider': 'deepseek', 'model': settings.deepseek_model, 'key_configured': settings.key_configured},
                'runtime': {'storage': 'owned-cards-sqlite; journeys-memory', 'prompt_version': PROMPT_VERSION,
                            'psychology_enabled': True, 'psychology_demo_mode': False,
                            'psychology_review_status': 'unreviewed', 'max_steps': settings.runtime_max_steps,
                            'max_context_chars': settings.runtime_max_context_chars}}

    @app.post('/api/support/sessions', status_code=201)
    async def create_session():
        store = current.get()
        if len(store.list()) >= 20:
            raise RuntimeFailure('session_limit_exceeded', '当前登录最多开启 20 次旅程，请退出后重新登录。')
        return store.create()

    @app.get('/api/support/sessions/{session_id}')
    async def get_session(session_id: UUID):
        return current.get().require(session_id).session.model_copy(deep=True)

    @app.post('/api/support/sessions/{session_id}/messages')
    async def send_message(session_id: UUID, body: ProductMessage, request: Request):
        store = current.get()
        record = store.require(session_id)
        permissions = getattr(record, 'product_permissions', {})
        previous = permissions.get(body.request_id)
        if previous is not None and previous != body.use_memories:
            raise RuntimeFailure('request_id_conflict', '请求编号不能用于不同的记忆授权。')
        limits.check(('model', request.state.owner), 40, 86400)
        # Recall is a per-turn permission; the builder sees no cards when declined.
        if record.lock.locked():
            raise RuntimeFailure('session_busy', '当前旅程正在处理，请稍后。')
        if getattr(record, 'recall_enabled', False) and not body.use_memories:
            await AgentOrchestrator(store, settings).clear_history(session_id)
        permissions[body.request_id] = body.use_memories
        record.product_permissions = permissions
        record.recall_enabled = body.use_memories
        model = model_factory() if model_factory else DeepSeekClient(settings, scheduler=request.app.state.scheduler)
        outgoing = SendMessageRequest.model_validate(body.model_dump(exclude={'model_consent', 'use_memories'}))
        result = await AgentOrchestrator(store, settings).handle_message(session_id, outgoing, model)
        payload = result.model_dump(mode='json')
        sources = payload.get('context_manifest', {}).get('sources', []) if payload.get('context_manifest') else []
        payload['memory_refs'] = [{'card_id': s['experience_card_id'], 'revision': s['experience_card_revision'],
                                   'title': s.get('experience_card_title', '已授权经历卡')} for s in sources if s.get('experience_card_id')]
        return payload

    @app.post('/api/support/sessions/{session_id}/workflow/cancel')
    async def cancel(session_id: UUID, body: CancelWorkflowRequest):
        return await AgentOrchestrator(current.get(), settings).cancel(session_id, body.run_id)

    @app.delete('/api/support/sessions/{session_id}/messages')
    async def clear(session_id: UUID):
        return await AgentOrchestrator(current.get(), settings).clear_history(session_id)

    @app.post('/api/support/sessions/{session_id}/end')
    async def end(session_id: UUID):
        return await AgentOrchestrator(current.get(), settings).end_session(session_id)

    @app.get('/api/product/cards')
    async def list_cards(request: Request):
        return await asyncio.to_thread(cards.list, request.state.owner)

    @app.post('/api/product/cards', status_code=201)
    async def save_card(body: SaveCard, request: Request):
        owner = request.state.owner
        record = current.get().require(body.session_id)
        payload = body.model_dump(mode='json')
        async with record.lock:
            current_store()
            replay = await asyncio.to_thread(cards.replay, owner, str(body.operation_id), payload)
            if replay is not None:
                return replay
            entry = record.understandings.entries.get(body.understanding_id)
            if not entry or entry.value.status != 'confirmed' or entry.value.confirmed_revision != body.expected_revision or entry.value.revision != body.expected_revision:
                raise RuntimeFailure('understanding_confirmation_required', '请先确认当前版本的理解。')
            fields = getattr(entry.value, 'fields', None)
            if fields is None:
                raise RuntimeFailure('understanding_fields_required', '当前理解缺少四字段，请重新核对。')
            return await asyncio.to_thread(cards.save, owner, str(body.operation_id), payload, fields=fields.model_dump())

    @app.patch('/api/product/cards/{card_id}')
    async def change_card(card_id: UUID, body: ChangeCard, request: Request):
        card = await asyncio.to_thread(cards.change, request.state.owner, str(card_id), body.expected_revision, remember=body.remember_for_future)
        await forget_active(request.state.owner)
        return card

    @app.delete('/api/product/cards/{card_id}', status_code=204)
    async def delete_card(card_id: UUID, request: Request, expected_revision: int = Query(ge=1)):
        await asyncio.to_thread(cards.change, request.state.owner, str(card_id), expected_revision, delete=True)
        await forget_active(request.state.owner)

    return app


# Defaults fail closed for production cookies until PRODUCT_ORIGIN is explicitly configured.
# uvicorn app.product.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
