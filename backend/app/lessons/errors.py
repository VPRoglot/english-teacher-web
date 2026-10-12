"""Доменные ошибки занятий (наследники `app.core.errors.AppError`)."""

from app.core.errors import Conflict, NotFound, ValidationFailed


class LessonNotFound(NotFound):
    code = "lesson_not_found"
    message = "Занятие не найдено"


class LessonNotStarted(Conflict):
    code = "lesson_not_started"
    message = "Отметить можно только начавшееся занятие"


class LessonNotEditable(Conflict):
    code = "lesson_not_editable"
    message = "Время, длительность и ссылку можно менять только у запланированного занятия"


class LessonNotDeletable(Conflict):
    code = "lesson_not_deletable"
    message = "Удалить можно только будущее запланированное занятие"


class LessonSlotTaken(Conflict):
    code = "lesson_slot_taken"
    message = "В это время уже есть занятие этого расписания"


class ScheduleRangeInvalid(ValidationFailed):
    """Период запроса занятий: конец позже начала, не больше 62 дней."""

    def __init__(self) -> None:
        super().__init__(
            details={
                "fields": [
                    {
                        "loc": ["query", "to"],
                        "message": "Период — не больше 62 дней, конец позже начала",
                        "type": "range",
                    }
                ]
            }
        )
