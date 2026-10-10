import re

from email_validator import EmailNotValidError, validate_email

from app.core.errors import ValidationFailed

_USERNAME = re.compile(r"[a-z0-9_.-]{3,32}")


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValidationFailed(
            "Некорректный email", code="invalid_email", details={"field": "email"}
        ) from exc
    return email


def normalize_username(value: str) -> str:
    username = value.strip().lower()
    if not _USERNAME.fullmatch(username):
        raise ValidationFailed(
            "Логин: 3–32 символа, латиница, цифры, точка, дефис, подчёркивание",
            code="invalid_username",
            details={"field": "username"},
        )
    return username
