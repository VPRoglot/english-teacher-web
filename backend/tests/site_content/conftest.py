from collections.abc import AsyncIterator
from io import BytesIO

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import login, make_family, make_parent, make_tutor


def make_image(
    fmt: str,
    size: tuple[int, int],
    *,
    mode: str = "RGB",
    exif: Image.Exif | None = None,
) -> bytes:
    """Картинка заданного формата в памяти; `exif` попадает в файл как есть."""
    image = Image.new(mode, size, 1 if mode == "1" else "teal")
    buffer = BytesIO()
    kwargs = {"exif": exif} if exif is not None else {}
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


@pytest.fixture
async def tutor_client(client: AsyncClient, db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    await make_tutor(db_session)
    await login(client, "tutor@example.com")
    yield client


@pytest.fixture
async def parent_client(
    client: AsyncClient, db_session: AsyncSession
) -> AsyncIterator[AsyncClient]:
    family = await make_family(db_session)
    await make_parent(db_session, family)
    await login(client, "parent@example.com")
    yield client
