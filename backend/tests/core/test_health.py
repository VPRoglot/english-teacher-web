from httpx import AsyncClient

from app.core.config import Settings
from app.main import create_app
from tests.conftest import open_client


async def test_health_returns_ok(client: AsyncClient) -> None:
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_docs_disabled_in_prod(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"app_env": "prod"}))
    async with open_client(app) as c:
        assert (await c.get("/api/docs")).status_code == 404
        assert (await c.get("/api/openapi.json")).status_code == 200
