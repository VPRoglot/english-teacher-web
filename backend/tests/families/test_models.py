import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Invitation, User, UserRole
from app.families.models import Child, ParentProfile
from tests.factories import make_child, make_family, make_parent, make_tutor


async def test_child_user_is_unique(db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    child = await make_child(db_session, fam, username="masha")
    db_session.add(Child(family_id=fam.id, user_id=child.user_id, full_name="Двойник"))
    with pytest.raises(IntegrityError, match="uq_children_user_id"):
        await db_session.flush()


async def test_birth_year_range(db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    db_session.add(Child(family_id=fam.id, full_name="Маша", birth_year=1900))
    with pytest.raises(IntegrityError, match="ck_children_birth_year_range"):
        await db_session.flush()


async def test_deleting_family_cascades(db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    child = await make_child(db_session, fam)
    await make_parent(db_session, fam)
    child_id = child.id
    await db_session.delete(fam)
    await db_session.flush()
    # CASCADE выполняется на стороне БД и не обновляет identity map сессии.
    db_session.expunge_all()
    assert await db_session.get(Child, child_id) is None
    assert (await db_session.scalar(select(func.count()).select_from(ParentProfile))) == 0


def _invitation(family_id: uuid.UUID, created_by: uuid.UUID) -> Invitation:
    return Invitation(
        token_hash="a" * 64,
        family_id=family_id,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        created_by=created_by,
    )


async def test_invitation_token_hash_unique(db_session: AsyncSession) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    db_session.add(_invitation(fam.id, tutor.id))
    await db_session.flush()
    db_session.add(_invitation(fam.id, tutor.id))
    with pytest.raises(IntegrityError, match="uq_invitations_token_hash"):
        await db_session.flush()


async def test_factories_build_consistent_family(db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    child = await make_child(db_session, fam, username="masha")
    assert child.user_id is not None
    user = await db_session.get(User, child.user_id)
    assert user is not None
    assert user.role is UserRole.CHILD
    assert user.username == "masha"
