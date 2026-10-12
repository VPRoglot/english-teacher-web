import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.families import service as families_service
from tests.factories import make_child, make_family


async def test_active_child_is_returned(db_session: AsyncSession) -> None:
    family = await make_family(db_session)
    child = await make_child(db_session, family)
    assert (await families_service.get_active_child(db_session, child.id)).id == child.id


async def test_missing_child_is_not_found(db_session: AsyncSession) -> None:
    with pytest.raises(NotFound) as caught:
        await families_service.get_active_child(db_session, uuid.uuid4())
    assert caught.value.code == "child_not_found"


async def test_archived_child_is_conflict(db_session: AsyncSession) -> None:
    family = await make_family(db_session)
    child = await make_child(db_session, family, archived=True)
    with pytest.raises(Conflict) as caught:
        await families_service.get_active_child(db_session, child.id)
    assert caught.value.code == "child_archived"
    assert caught.value.message == "Ученик в архиве"


async def test_child_of_archived_family_is_conflict(db_session: AsyncSession) -> None:
    family = await make_family(db_session, archived=True)
    child = await make_child(db_session, family)
    with pytest.raises(Conflict) as caught:
        await families_service.get_active_child(db_session, child.id)
    assert caught.value.code == "family_archived"
