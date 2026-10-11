from fastapi import APIRouter, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import TutorUser
from app.core.config import Settings
from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES
from app.core.tasks import TaskQueue, TaskQueueDep
from app.site_content import service as site_service
from app.site_content.errors import FileTooLarge
from app.site_content.images import MAX_UPLOAD_BYTES
from app.site_content.models import BlockKey
from app.site_content.schemas import (
    AboutBlock,
    ContactsBlock,
    FaqBlock,
    HeroBlock,
    MediaOut,
    ReviewsBlock,
    ServicesBlock,
    SiteBlocksAdmin,
)
from app.site_content.storage import MediaStorageDep

router = APIRouter(prefix="/admin", tags=["admin"], responses=API_ERROR_RESPONSES)


@router.post("/media", status_code=201)
async def upload_media(
    file: UploadFile,
    request: Request,
    _: TutorUser,
    session: DbSession,
    storage: MediaStorageDep,
) -> MediaOut:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise FileTooLarge
    settings: Settings = request.app.state.settings
    return await site_service.upload_media(session, storage, settings, data)


@router.get("/site-blocks")
async def get_site_blocks(request: Request, _: TutorUser, session: DbSession) -> SiteBlocksAdmin:
    settings: Settings = request.app.state.settings
    return await site_service.get_site_blocks(session, settings)


async def _save_and_revalidate(
    session: AsyncSession, queue: TaskQueue, key: BlockKey, block: BaseModel
) -> None:
    await site_service.save_block(session, key, block)
    # Коммит до постановки задачи: задача должна увидеть закоммиченные данные,
    # иначе Next закеширует старый контент.
    await session.commit()
    await site_service.request_site_revalidation(queue)


@router.put("/site-blocks/hero")
async def update_hero_block(
    body: HeroBlock, _: TutorUser, session: DbSession, queue: TaskQueueDep
) -> HeroBlock:
    await _save_and_revalidate(session, queue, BlockKey.HERO, body)
    return body


@router.put("/site-blocks/about")
async def update_about_block(
    body: AboutBlock, _: TutorUser, session: DbSession, queue: TaskQueueDep
) -> AboutBlock:
    await _save_and_revalidate(session, queue, BlockKey.ABOUT, body)
    return body


@router.put("/site-blocks/services")
async def update_services_block(
    body: ServicesBlock, _: TutorUser, session: DbSession, queue: TaskQueueDep
) -> ServicesBlock:
    await _save_and_revalidate(session, queue, BlockKey.SERVICES, body)
    return body


@router.put("/site-blocks/reviews")
async def update_reviews_block(
    body: ReviewsBlock, _: TutorUser, session: DbSession, queue: TaskQueueDep
) -> ReviewsBlock:
    await _save_and_revalidate(session, queue, BlockKey.REVIEWS, body)
    return body


@router.put("/site-blocks/faq")
async def update_faq_block(
    body: FaqBlock, _: TutorUser, session: DbSession, queue: TaskQueueDep
) -> FaqBlock:
    await _save_and_revalidate(session, queue, BlockKey.FAQ, body)
    return body


@router.put("/site-blocks/contacts")
async def update_contacts_block(
    body: ContactsBlock, _: TutorUser, session: DbSession, queue: TaskQueueDep
) -> ContactsBlock:
    await _save_and_revalidate(session, queue, BlockKey.CONTACTS, body)
    return body
