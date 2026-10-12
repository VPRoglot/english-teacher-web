"""Планировщик Taskiq: ставит в очередь задачи с меткой `schedule` (например, ежедневную
материализацию серий занятий). Запускается отдельным процессом в ровно одном экземпляре:
`taskiq scheduler app.scheduler:scheduler`.
"""

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

import app.worker
from app.core.observability import init_sentry

# Sentry в worker включается в его стартовом хуке (setup_worker), в scheduler этот хук не
# срабатывает, поэтому процесс планировщика инициализирует Sentry сам, один раз.
init_sentry(app.worker.settings, "scheduler")

scheduler = TaskiqScheduler(
    broker=app.worker.broker, sources=[LabelScheduleSource(app.worker.broker)]
)
