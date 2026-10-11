"""Планировщик Taskiq: ставит в очередь задачи с меткой `schedule` (например, ежедневную
материализацию серий занятий). Запускается отдельным процессом в ровно одном экземпляре:
`taskiq scheduler app.scheduler:scheduler`.
"""

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource

import app.worker

scheduler = TaskiqScheduler(
    broker=app.worker.broker, sources=[LabelScheduleSource(app.worker.broker)]
)
