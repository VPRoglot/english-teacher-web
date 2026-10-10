import pytest

from app.auth.identity import normalize_email, normalize_username
from app.core.errors import ValidationFailed


def test_normalize_email_strips_and_lowercases() -> None:
    assert normalize_email("  Tutor@Mail.RU ") == "tutor@mail.ru"


@pytest.mark.parametrize("bad", ["", "not-an-email", "a@", "@b.ru"])
def test_normalize_email_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValidationFailed) as e:
        normalize_email(bad)
    assert e.value.code == "invalid_email"
    assert e.value.details == {"field": "email"}


def test_normalize_username() -> None:
    assert normalize_username(" Masha_2015 ") == "masha_2015"


@pytest.mark.parametrize("bad", ["ab", "x" * 33, "маша", "a b"])
def test_normalize_username_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValidationFailed) as e:
        normalize_username(bad)
    assert e.value.code == "invalid_username"
