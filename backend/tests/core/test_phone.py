import pytest

from app.core.phone import normalize_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8 (999) 123-45-67", "+79991234567"),
        ("999 123-45-67", "+79991234567"),
        ("+7 999 123 45 67", "+79991234567"),
        ("+44 20 7946 0958", "+442079460958"),
    ],
)
def test_normalize_phone(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["4951234567", "12345", "abc", "+٧٩٩٩١٢٣٤٥٦٧"])
def test_normalize_phone_rejects(raw: str) -> None:
    with pytest.raises(ValueError, match="Укажите телефон"):
        normalize_phone(raw)
