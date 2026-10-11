import re

PHONE_ERROR = "Укажите телефон в формате +7 999 123-45-67"

_SEPARATORS = re.compile(r"[\s\-()]")
_PHONE_RE = re.compile(r"\+?[0-9]{10,15}")
_RU_TRUNK_RE = re.compile(r"8([0-9]{10})")  # 8XXXXXXXXXX
_RU_MOBILE_RE = re.compile(r"9[0-9]{9}")  # без кода страны: 999 123-45-67
_BARE_TEN_DIGITS_RE = re.compile(r"[0-9]{10}")


def normalize_phone(value: str) -> str:
    """Приводит телефон к виду «+цифры»; при неверном формате бросает ValueError(PHONE_ERROR)."""
    number = _SEPARATORS.sub("", value)
    if trunk := _RU_TRUNK_RE.fullmatch(number):
        number = f"+7{trunk.group(1)}"
    elif _RU_MOBILE_RE.fullmatch(number):
        number = f"+7{number}"
    elif _BARE_TEN_DIGITS_RE.fullmatch(number):
        raise ValueError(PHONE_ERROR)  # десять цифр без «+» — не российский мобильный
    if not _PHONE_RE.fullmatch(number):
        raise ValueError(PHONE_ERROR)
    return "+" + number.removeprefix("+")
