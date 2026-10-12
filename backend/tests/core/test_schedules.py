from taskiq import InMemoryBroker
from taskiq.schedule_sources import LabelScheduleSource

from app.leads.tasks import ANONYMIZE_LEADS_TASK
from app.lessons.tasks import MATERIALIZE_SERIES_TASK
from app.tasks import setup_worker
from tests.conftest import make_settings


async def test_label_schedule_source_lists_daily_tasks() -> None:
    broker = setup_worker(InMemoryBroker(), make_settings())
    source = LabelScheduleSource(broker)
    await source.startup()
    schedules = await source.get_schedules()
    assert {(s.task_name, s.cron) for s in schedules} == {
        (MATERIALIZE_SERIES_TASK, "0 1 * * *"),
        (ANONYMIZE_LEADS_TASK, "30 1 * * *"),
    }
