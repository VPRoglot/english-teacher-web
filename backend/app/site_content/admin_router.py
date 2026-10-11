from fastapi import APIRouter, Request, UploadFile

from app.auth.deps import TutorUser
from app.core.config import Settings
from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES
from app.site_content import service as site_service
from app.site_content.errors import FileTooLarge
from app.site_content.images import MAX_UPLOAD_BYTES
from app.site_content.schemas import MediaOut
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
