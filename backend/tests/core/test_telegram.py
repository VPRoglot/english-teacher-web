import pytest

from app.core.telegram import strip_telegram_handle


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@olga_test", "olga_test"),
        ("olga_test", "olga_test"),
        ("https://t.me/olga_test", "olga_test"),
        ("http://t.me/olga_test", "olga_test"),
        ("t.me/olga_test", "olga_test"),
        ("HTTPS://T.ME/Olga_Test", "Olga_Test"),
        ("  @olga_test  ", "olga_test"),
        ("olga test", "olga test"),
        ("@", ""),
        ("", ""),
    ],
)
def test_strip_telegram_handle(raw: str, expected: str) -> None:
    assert strip_telegram_handle(raw) == expected
