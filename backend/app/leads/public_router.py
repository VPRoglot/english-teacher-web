import structlog
from fastapi import APIRouter, Request
from redis.exceptions import RedisError

from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES, RateLimited
from app.core.rate_limit import RateLimit, RateLimiter
from app.core.redis import RedisClient
from app.core.tasks import TaskQueueDep
from app.leads import service
from app.leads.captcha import CaptchaDep, CaptchaFailed
from app.leads.schemas import LeadAccepted, LeadCreate

log = structlog.get_logger("app.leads")

router = APIRouter(prefix="/public", tags=["public"], responses=API_ERROR_RESPONSES)

LEAD_RATE_LIMIT = RateLimit(limit=3, window_seconds=3600)  # заявок с одного IP в час


async def _exceeded_retry_after(limiter: RateLimiter, key: str) -> int | None:
    """Секунды до конца окна, если лимит заявок превышен; иначе `None`.

    Fail-open: пока Redis недоступен, заявку принимаем без лимита (защищают honeypot и капча) —
    потерянная заявка хуже спама.
    """
    try:
        if await limiter.hit(key, LEAD_RATE_LIMIT) <= LEAD_RATE_LIMIT.limit:
            return None
        retry_after = await limiter.retry_after(key, LEAD_RATE_LIMIT)
    except (RedisError, TimeoutError, OSError):
        log.warning("lead_rate_limit_unavailable", exc_info=True)
        return None
    return retry_after or LEAD_RATE_LIMIT.window_seconds


@router.post("/leads", status_code=201)
async def submit_lead(
    body: LeadCreate,
    request: Request,
    session: DbSession,
    queue: TaskQueueDep,
    captcha: CaptchaDep,
    redis: RedisClient,
) -> LeadAccepted:
    # За прокси IP берётся из `request.client` — проброс X-Forwarded-For настраивается отдельно.
    ip = request.client.host if request.client else None
    limiter = RateLimiter(redis)
    key = f"lead:ip:{ip or 'unknown'}"
    # Попытка учитывается атомарно и до остальных проверок: honeypot и капча лимит не обходят.
    retry_after = await _exceeded_retry_after(limiter, key)
    if retry_after is not None:
        raise RateLimited(retry_after)

    if body.website:
        # Бот получает такой же ответ, как человек, и не понимает, что попался.
        log.info("lead_honeypot", ip=ip)
        return LeadAccepted()

    if not await captcha.verify(body.captcha_token, ip):
        raise CaptchaFailed()

    lead = await service.create_lead(session, body)
    # Коммит до постановки задачи: worker должен увидеть закоммиченную заявку.
    await session.commit()
    await service.request_lead_notification(queue, lead.id)
    return LeadAccepted()
