import uuid
from datetime import UTC, datetime, timedelta

import pytest
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import Context

from app.lessons.models import ChangeRequest, ChangeRequestStatus, ChangeRequestType
from app.lessons.requests_service import NOTIFY_CHANGE_REQUEST_TASK
from app.lessons.schemas import TutorSettingsUpdate
from app.lessons.tutor_settings import update_tutor_settings
from app.notifications.notifier import DisabledNotifier, NotifyFailed
from app.notifications.tasks import format_change_request_message, notify_change_request
from tests.factories import make_child, make_family
from tests.lessons.conftest import make_change_request, make_lesson
from tests.notifications.conftest import PUBLIC_BASE_URL, FakeNotifier

URL = "https://t.example/admin/requests"


def test_message_for_late_cancel() -> None:
    text = format_change_request_message(
        type=ChangeRequestType.CANCEL,
        child_name="Маша",
        starts_at_local="20.10.2026 18:00",
        is_late=True,
        admin_url=URL,
    )
    assert text.splitlines() == [
        "Запрос на отмену занятия",
        "Ученик: Маша",
        "Занятие: 20.10.2026 18:00",
        "Поздняя отмена",
        URL,
    ]


def test_message_for_reschedule_has_no_late_line() -> None:
    text = format_change_request_message(
        type=ChangeRequestType.RESCHEDULE,
        child_name="Маша",
        starts_at_local="20.10.2026 18:00",
        is_late=False,
        admin_url=URL,
    )
    assert text.splitlines() == [
        "Запрос на перенос занятия",
        "Ученик: Маша",
        "Занятие: 20.10.2026 18:00",
        URL,
    ]


@pytest.fixture
async def db_request(db_session: AsyncSession) -> ChangeRequest:
    family = await make_family(db_session)
    child = await make_child(db_session, family, full_name="Маша")
    # 13:00 UTC = 18:00 YEKT (UTC+5); запрос подан за 2 часа — отмена поздняя.
    starts_at = datetime(2026, 10, 20, 13, 0, tzinfo=UTC)
    lesson = await make_lesson(db_session, child=child, starts_at=starts_at)
    request = await make_change_request(
        db_session,
        lesson,
        type=ChangeRequestType.CANCEL,
        comment="Секретный комментарий родителя",
        created_at=starts_at - timedelta(hours=2),
    )
    await update_tutor_settings(
        db_session,
        TutorSettingsUpdate(timezone="Asia/Yekaterinburg", cancel_policy_hours=24),
        now=starts_at - timedelta(days=3),
    )
    return request


async def test_sends_once_in_tutor_timezone(
    context: Context, db_request: ChangeRequest, notifier: FakeNotifier, db_session: AsyncSession
) -> None:
    await notify_change_request(str(db_request.id), context)
    await notify_change_request(str(db_request.id), context)

    assert notifier.sent == [
        "Запрос на отмену занятия\n"
        "Ученик: Маша\n"
        "Занятие: 20.10.2026 18:00\n"
        "Поздняя отмена\n"
        f"{PUBLIC_BASE_URL}/admin/requests"
    ]
    assert "Секретный" not in notifier.sent[0]
    await db_session.refresh(db_request)
    assert db_request.notified_at is not None


@pytest.mark.parametrize("request_id", [str(uuid.uuid4()), "not-a-uuid"])
async def test_missing_request_is_noop(
    context: Context, notifier: FakeNotifier, request_id: str
) -> None:
    with structlog.testing.capture_logs() as logs:
        await notify_change_request(request_id, context)
    assert notifier.sent == []
    assert [(e["event"], e["log_level"], e["reason"]) for e in logs] == [
        ("change_request_notification_skipped", "info", "not_found")
    ]


async def test_resolved_request_is_noop(
    context: Context, db_request: ChangeRequest, notifier: FakeNotifier, db_session: AsyncSession
) -> None:
    db_request.status = ChangeRequestStatus.WITHDRAWN
    db_request.resolved_at = datetime.now(UTC)
    await db_session.flush()
    with structlog.testing.capture_logs() as logs:
        await notify_change_request(str(db_request.id), context)
    assert notifier.sent == []
    assert [(e["event"], e["log_level"], e["reason"]) for e in logs] == [
        ("change_request_notification_skipped", "info", "not_pending")
    ]


async def test_already_notified_request_is_skipped(
    context: Context, db_request: ChangeRequest, notifier: FakeNotifier, db_session: AsyncSession
) -> None:
    db_request.notified_at = datetime.now(UTC)
    await db_session.flush()
    with structlog.testing.capture_logs() as logs:
        await notify_change_request(str(db_request.id), context)
    assert notifier.sent == []
    assert [e["reason"] for e in logs] == ["already_notified"]


async def test_failure_leaves_unnotified(
    context: Context, db_request: ChangeRequest, notifier: FakeNotifier, db_session: AsyncSession
) -> None:
    notifier.error = NotifyFailed("Telegram ответил 500")
    with pytest.raises(NotifyFailed):
        await notify_change_request(str(db_request.id), context)
    await db_session.refresh(db_request)
    assert db_request.notified_at is None

    notifier.error = None
    await notify_change_request(str(db_request.id), context)
    assert len(notifier.sent) == 1
    await db_session.refresh(db_request)
    assert db_request.notified_at is not None


async def test_disabled_notifier_keeps_notified_at_null(
    context: Context, db_request: ChangeRequest, db_session: AsyncSession
) -> None:
    context.state.notifier = DisabledNotifier()
    with structlog.testing.capture_logs() as logs:
        await notify_change_request(str(db_request.id), context)
    await db_session.refresh(db_request)
    assert db_request.notified_at is None
    assert [(e["event"], e["log_level"], e["reason"]) for e in logs] == [
        ("change_request_notification_skipped", "warning", "disabled")
    ]


def test_task_name_matches_enqueue_constant() -> None:
    assert NOTIFY_CHANGE_REQUEST_TASK == "notifications.notify_change_request"
