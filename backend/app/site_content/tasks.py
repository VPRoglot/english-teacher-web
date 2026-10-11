from typing import Annotated, Protocol

import httpx
from taskiq import AsyncBroker, Context, TaskiqDepends

from app.core.request_id import REQUEST_ID_HEADER, get_request_id

REVALIDATE_SITE_TASK = "site_content.revalidate_site"


class RevalidateFailed(Exception):
    """Next не принял запрос на сброс кеша: задача будет повторена."""


class Revalidator(Protocol):
    async def revalidate(self) -> None: ...


class HttpRevalidator(Revalidator):
    def __init__(self, client: httpx.AsyncClient, url: str, secret: str) -> None:
        self._client = client
        self._url = url
        self._secret = secret

    async def revalidate(self) -> None:
        headers = {"Authorization": f"Bearer {self._secret}"}
        request_id = get_request_id()
        if request_id:
            headers[REQUEST_ID_HEADER] = request_id
        try:
            response = await self._client.post(self._url, headers=headers)
        except httpx.HTTPError as exc:
            raise RevalidateFailed(f"Next недоступен: {type(exc).__name__}") from exc
        if not response.is_success:
            raise RevalidateFailed(f"Next ответил {response.status_code}")


async def revalidate_site(context: Annotated[Context, TaskiqDepends()]) -> None:
    await context.state.revalidator.revalidate()


def register_tasks(broker: AsyncBroker) -> None:
    broker.register_task(
        revalidate_site, task_name=REVALIDATE_SITE_TASK, retry_on_error=True, max_retries=5
    )
