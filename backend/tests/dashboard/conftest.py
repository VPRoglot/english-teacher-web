from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import login, make_family, make_parent, make_tutor


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
