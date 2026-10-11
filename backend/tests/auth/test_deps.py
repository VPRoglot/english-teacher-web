from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser, FamilyMember, ParentUser, TutorUser
from tests.factories import login, make_child, make_family, make_parent, make_tutor


def _add_probe_routes(app: FastAPI) -> None:
    @app.get("/api/_probe/any")
    async def probe_any(user: CurrentUser) -> dict[str, str]:
        return {"role": user.role}

    @app.get("/api/_probe/tutor")
    async def probe_tutor(user: TutorUser) -> dict[str, str]:
        return {"role": user.role}

    @app.get("/api/_probe/parent")
    async def probe_parent(user: ParentUser) -> dict[str, str]:
        return {"role": user.role}

    @app.get("/api/_probe/family")
    async def probe_family(user: FamilyMember) -> dict[str, str]:
        return {"role": user.role}


async def test_role_dependencies(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    _add_probe_routes(app)
    fam = await make_family(db_session)
    await make_tutor(db_session)
    await make_parent(db_session, fam)
    await make_child(db_session, fam, username="masha")

    anonymous = {p: (await client.get(f"/api/_probe/{p}")).status_code for p in ("tutor", "family")}
    assert anonymous == {"tutor": 401, "family": 401}

    # (логин, any, tutor, parent, family): чужая роль получает 404, а не 403.
    expected = {
        "tutor@example.com": (200, 200, 404, 404),
        "parent@example.com": (200, 404, 200, 200),
        "masha": (200, 404, 404, 200),
    }
    for login_, codes in expected.items():
        await login(client, login_)
        got = tuple(
            [
                (await client.get(f"/api/_probe/{p}")).status_code
                for p in ("any", "tutor", "parent", "family")
            ]
        )
        assert got == codes, login_
        await client.post("/api/auth/logout")

    r = await client.get("/api/_probe/tutor")
    assert r.status_code == 401
