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


class SeriesNotFound(NotFound):
    code = "series_not_found"
    message = "Расписание не найдено"


class SeriesArchived(Conflict):
    code = "series_archived"
    message = "Расписание уже завершено"


class SeriesDateInvalid(ValidationFailed):
    """Дата правки серии не подходит: ошибка на указанном поле запроса."""

    def __init__(self, loc: list[str], message: str) -> None:
        super().__init__(details={"fields": [{"loc": loc, "message": message, "type": "range"}]})


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


class ChangeRequestNotFound(NotFound):
    code = "change_request_not_found"
    message = "Запрос не найден"


class ChangeRequestExists(Conflict):
    code = "change_request_exists"
    message = "По этому занятию уже есть запрос — дождитесь ответа репетитора"


class LessonNotRequestable(Conflict):
    code = "lesson_not_requestable"
    message = "Запрос можно подать только по будущему запланированному занятию"


class ChangeRequestNotPending(Conflict):
    code = "change_request_not_pending"
    message = "Запрос уже рассмотрен или отозван"


class ChangeRequestOutdated(Conflict):
    code = "change_request_outdated"
    message = "Занятие уже изменено — отклоните запрос с комментарием"


class NewStartsAtRequired(ValidationFailed):
    """Для одобрения переноса не указано новое время."""

    def __init__(self) -> None:
        super().__init__(
            details={
                "fields": [
                    {
                        "loc": ["body", "new_starts_at"],
                        "message": "Укажите новое время",
                        "type": "missing",
                    }
                ]
            }
        )
