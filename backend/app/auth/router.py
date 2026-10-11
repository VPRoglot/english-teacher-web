from fastapi import APIRouter, Request, Response

from app.auth import service
from app.auth.deps import CurrentUser
from app.auth.schemas import LoginRequest, MeResponse
from app.auth.sessions import (
    SESSION_COOKIE,
    SessionStoreDep,
    clear_session_cookie,
    set_session_cookie,
)
from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES, RateLimited
from app.core.rate_limit import RateLimit, RateLimiter
from app.core.redis import RedisClient

router = APIRouter(prefix="/auth", tags=["auth"], responses=API_ERROR_RESPONSES)

LOGIN_PAIR = RateLimit(5, 900)  # неудачные попытки на пару «логин + IP» за 15 минут
LOGIN_IP = RateLimit(30, 900)  # неудачные попытки с одного IP за 15 минут


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: DbSession,
    store: SessionStoreDep,
    redis: RedisClient,
) -> MeResponse:
    # За прокси IP берётся из `request.client` — проброс X-Forwarded-For настраивается отдельно.
    ip = request.client.host if request.client else "unknown"
    pair_key = f"login:{service.normalize_login(body.login)}:{ip}"
    ip_key = f"login-ip:{ip}"
    limiter = RateLimiter(redis)

    # Попытка учитывается атомарно ДО проверки пароля: параллельная пачка запросов не проходит
    # проверку лимита одновременно, а верный пароль не обходит исчерпанный лимит.
    pair_count = await limiter.hit(pair_key, LOGIN_PAIR)
    ip_count = await limiter.hit(ip_key, LOGIN_IP)
    waits: list[int] = []
    for key, rule, count in ((pair_key, LOGIN_PAIR, pair_count), (ip_key, LOGIN_IP, ip_count)):
        if count > rule.limit:
            waits.append(await limiter.retry_after(key, rule) or rule.window_seconds)
    if waits:
        raise RateLimited(max(waits))

    user = await service.authenticate(session, login=body.login, password=body.password)
    if user is None:
        raise service.InvalidCredentials()

    me = await service.build_me(session, user)
    # Успешный вход не расходует бюджет: счётчик пары сбрасывается, IP получает попытку назад.
    await limiter.reset(pair_key)
    await limiter.decr(ip_key)
    # Ротация: прежняя сессия из cookie запроса отзывается, выдаётся новая.
    old_token = request.cookies.get(SESSION_COOKIE)
    if old_token:
        await store.delete(old_token)
    token = await store.create(user.id, user.role)
    set_session_cookie(response, token, user.role, request.app.state.settings)
    return me


@router.post("/logout", status_code=204, response_class=Response)
async def logout(request: Request, store: SessionStoreDep) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await store.delete(token)
    response = Response(status_code=204)
    clear_session_cookie(response, request.app.state.settings)
    return response


@router.get("/me")
async def get_me(user: CurrentUser, session: DbSession) -> MeResponse:
    return await service.build_me(session, user)
