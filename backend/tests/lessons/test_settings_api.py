from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

DEFAULTS = {"timezone": "Europe/Moscow", "cancel_policy_hours": 24}


async def test_tutor_reads_and_updates_settings(tutor_client: AsyncClient) -> None:
    assert (await tutor_client.get("/api/admin/settings")).json() == DEFAULTS
    r = await tutor_client.put(
        "/api/admin/settings", json={"timezone": "Asia/Yekaterinburg", "cancel_policy_hours": 12}
    )
    assert r.status_code == 200
    assert r.json() == {"timezone": "Asia/Yekaterinburg", "cancel_policy_hours": 12}
    again = await tutor_client.get("/api/admin/settings")
    assert again.json()["timezone"] == "Asia/Yekaterinburg"
    # Возвращаем значения по умолчанию: синглтон общий для тестов (откат транзакции — страховка).
    restored = await tutor_client.put("/api/admin/settings", json=DEFAULTS)
    assert restored.json() == DEFAULTS


async def test_settings_changes_do_not_leak_between_tests(
    tutor_client: AsyncClient, engine: AsyncEngine
) -> None:
    r = await tutor_client.put(
        "/api/admin/settings", json={"timezone": "Asia/Tokyo", "cancel_policy_hours": 1}
    )
    assert r.status_code == 200
    # Другое соединение (как следующий тест) не видит изменений откатываемой транзакции.
    async with engine.connect() as other:
        result = await other.execute(
            text("SELECT timezone, cancel_policy_hours FROM tutor_settings")
        )
        row = result.one()
    assert tuple(row) == ("Europe/Moscow", 24)


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"timezone": "Mars/Base", "cancel_policy_hours": 24}, "timezone"),
        ({"timezone": "", "cancel_policy_hours": 24}, "timezone"),
        ({"timezone": "E" * 65, "cancel_policy_hours": 24}, "timezone"),
        ({"timezone": "Europe/Moscow", "cancel_policy_hours": 169}, "cancel_policy_hours"),
        ({"timezone": "Europe/Moscow", "cancel_policy_hours": -1}, "cancel_policy_hours"),
        ({"timezone": "Europe/Moscow"}, "cancel_policy_hours"),
    ],
)
async def test_invalid_settings_are_422(
    tutor_client: AsyncClient, body: dict[str, Any], field: str
) -> None:
    r = await tutor_client.put("/api/admin/settings", json=body)
    assert r.status_code == 422
    assert [f["loc"][-1] for f in r.json()["error"]["details"]["fields"]] == [field]
    assert (await tutor_client.get("/api/admin/settings")).json() == DEFAULTS


async def test_unknown_timezone_message(tutor_client: AsyncClient) -> None:
    r = await tutor_client.put(
        "/api/admin/settings", json={"timezone": "Mars/Base", "cancel_policy_hours": 24}
    )
    assert "Неизвестный часовой пояс" in r.json()["error"]["details"]["fields"][0]["message"]


@pytest.mark.parametrize("hours", [0, 168])
async def test_policy_bounds_are_allowed(tutor_client: AsyncClient, hours: int) -> None:
    r = await tutor_client.put(
        "/api/admin/settings", json={"timezone": "Europe/Berlin", "cancel_policy_hours": hours}
    )
    assert r.status_code == 200
    assert r.json() == {"timezone": "Europe/Berlin", "cancel_policy_hours": hours}


async def test_family_reads_schedule_settings(parent_client: AsyncClient) -> None:
    r = await parent_client.get("/api/me/schedule-settings")
    assert r.status_code == 200
    assert r.json() == DEFAULTS


async def test_child_reads_schedule_settings(child_client: AsyncClient) -> None:
    r = await child_client.get("/api/me/schedule-settings")
    assert r.status_code == 200
    assert r.json() == DEFAULTS


async def test_settings_admin_only(parent_client: AsyncClient) -> None:
    body = {"timezone": "Europe/Moscow", "cancel_policy_hours": 24}
    assert (await parent_client.get("/api/admin/settings")).status_code == 404
    assert (await parent_client.put("/api/admin/settings", json=body)).status_code == 404


async def test_tutor_has_no_cabinet_settings(tutor_client: AsyncClient) -> None:
    assert (await tutor_client.get("/api/me/schedule-settings")).status_code == 404


async def test_anonymous_requests_are_401(client: AsyncClient) -> None:
    body = {"timezone": "Europe/Moscow", "cancel_policy_hours": 24}
    assert (await client.get("/api/admin/settings")).status_code == 401
    assert (await client.put("/api/admin/settings", json=body)).status_code == 401
    assert (await client.get("/api/me/schedule-settings")).status_code == 401


def _settings_selects(sql_log: list[str]) -> list[str]:
    return [s for s in sql_log if "FROM tutor_settings" in s and s.lstrip().startswith("SELECT")]


async def test_settings_update_reads_the_row_for_update(
    tutor_client: AsyncClient, sql_log: list[str]
) -> None:
    r = await tutor_client.put("/api/admin/settings", json=DEFAULTS)

    assert r.status_code == 200
    selects = _settings_selects(sql_log)
    assert selects and all(s.rstrip().endswith("FOR UPDATE") for s in selects)


async def test_settings_read_is_not_locked(tutor_client: AsyncClient, sql_log: list[str]) -> None:
    assert (await tutor_client.get("/api/admin/settings")).status_code == 200
    assert not any("FOR " in s for s in _settings_selects(sql_log))
