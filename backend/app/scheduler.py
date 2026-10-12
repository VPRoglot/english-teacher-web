"""Планировщик Taskiq: ставит в очередь задачи с меткой `schedule` (например, ежедневную
материализацию серий занятий). Запускается отдельным процессом в ровно одном экземпляре:
`taskiq scheduler app.scheduler:scheduler`.
"""

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

import app.worker
from app.core.observability import init_sentry

# Импорт app.worker уже включил Sentry с тегом worker: переинициализация задаёт тег scheduler.
init_sentry(app.worker.settings, "scheduler")

scheduler = TaskiqScheduler(
    broker=app.worker.broker, sources=[LabelScheduleSource(app.worker.broker)]
)
