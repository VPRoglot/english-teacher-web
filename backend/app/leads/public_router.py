import structlog
from fastapi import APIRouter, Request

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
    if await limiter.hit(key, LEAD_RATE_LIMIT) > LEAD_RATE_LIMIT.limit:
        retry_after = await limiter.retry_after(key, LEAD_RATE_LIMIT)
        raise RateLimited(retry_after or LEAD_RATE_LIMIT.window_seconds)

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
