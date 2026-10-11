import re
import uuid
from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.core.config import Settings
from app.site_content.models import BlockKey

TELEGRAM_ERROR = "Укажите имя пользователя Telegram, например @anna_english"
PHONE_ERROR = "Укажите телефон в формате +7 999 123-45-67"

_TELEGRAM_PREFIXES = ("https://t.me/", "http://t.me/", "t.me/", "@")
_TELEGRAM_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")
_PHONE_SEPARATORS = re.compile(r"[\s\-()]")
_PHONE_RE = re.compile(r"\+?[0-9]{10,15}")
_RU_TRUNK_RE = re.compile(r"8([0-9]{10})")  # 8XXXXXXXXXX
_RU_MOBILE_RE = re.compile(r"9[0-9]{9}")  # без кода страны: 999 123-45-67
_BARE_TEN_DIGITS_RE = re.compile(r"[0-9]{10}")


def _text(max_length: int, *, min_length: int = 1) -> Any:
    return StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)


Name = Annotated[str, _text(100)]
Title = Annotated[str, _text(120)]
Subtitle = Annotated[str, _text(300)]
CtaText = Annotated[str, _text(40)]
Markdown = Annotated[str, _text(5000)]
Credential = Annotated[str, _text(200)]
ServiceDescription = Annotated[str, _text(1000, min_length=0)]
ServiceFormat = Annotated[str, _text(60)]
ReviewText = Annotated[str, _text(2000)]
Question = Annotated[str, _text(300)]
WorkingHours = Annotated[str, _text(200)]


class _Block(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class HeroBlock(_Block):
    name: Name
    title: Title
    subtitle: Subtitle
    photo_media_id: uuid.UUID | None = None
    cta_text: CtaText


class AboutBlock(_Block):
    text: Markdown
    photo_media_id: uuid.UUID | None = None
    credentials: list[Credential] = Field(max_length=20)


class ServiceItem(_Block):
    title: Title
    description: ServiceDescription
    duration_min: int = Field(ge=15, le=240)
    price_rub: int = Field(ge=0, le=100_000)
    format: ServiceFormat


class ServicesBlock(_Block):
    items: list[ServiceItem] = Field(max_length=20)


class ReviewItem(_Block):
    author: Name
    text: ReviewText
    child_age: int | None = Field(default=None, ge=3, le=18)
    photo_media_id: uuid.UUID | None = None


class ReviewsBlock(_Block):
    items: list[ReviewItem] = Field(max_length=30)


class FaqItem(_Block):
    question: Question
    answer: ReviewText


class FaqBlock(_Block):
    items: list[FaqItem] = Field(max_length=30)


class ContactsBlock(_Block):
    telegram: str | None = None
    whatsapp: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    working_hours_text: WorkingHours | None = None

    @field_validator("telegram", "whatsapp", "phone", "email", "working_hours_text", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("telegram", mode="after")
    @classmethod
    def _normalize_telegram(cls, value: str | None) -> str | None:
        if value is None:
            return None
        username = value.strip()
        for prefix in _TELEGRAM_PREFIXES:
            if username.startswith(prefix):
                username = username.removeprefix(prefix)
        if not _TELEGRAM_RE.fullmatch(username):
            raise ValueError(TELEGRAM_ERROR)
        return username

    @field_validator("whatsapp", "phone", mode="after")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        number = _PHONE_SEPARATORS.sub("", value)
        if trunk := _RU_TRUNK_RE.fullmatch(number):
            number = f"+7{trunk.group(1)}"
        elif _RU_MOBILE_RE.fullmatch(number):
            number = f"+7{number}"
        elif _BARE_TEN_DIGITS_RE.fullmatch(number):
            raise ValueError(PHONE_ERROR)  # десять цифр без «+» — не российский мобильный
        if not _PHONE_RE.fullmatch(number):
            raise ValueError(PHONE_ERROR)
        return "+" + number.removeprefix("+")


BLOCK_SCHEMAS: Mapping[BlockKey, type[BaseModel]] = {
    BlockKey.HERO: HeroBlock,
    BlockKey.ABOUT: AboutBlock,
    BlockKey.SERVICES: ServicesBlock,
    BlockKey.REVIEWS: ReviewsBlock,
    BlockKey.FAQ: FaqBlock,
    BlockKey.CONTACTS: ContactsBlock,
}


def referenced_media_ids(block: BaseModel) -> list[tuple[tuple[str | int, ...], uuid.UUID]]:
    """Пары «путь поля → id фото» для всех ссылок на media в блоке (None пропускаются)."""
    if isinstance(block, HeroBlock | AboutBlock):
        photo_id = block.photo_media_id
        return [(("photo_media_id",), photo_id)] if photo_id is not None else []
    if isinstance(block, ReviewsBlock):
        return [
            (("items", index, "photo_media_id"), item.photo_media_id)
            for index, item in enumerate(block.items)
            if item.photo_media_id is not None
        ]
    return []


class MediaOut(BaseModel):
    id: uuid.UUID
    url: str
    content_type: str
    size_bytes: int
    width: int
    height: int


def media_url(settings: Settings, s3_key: str) -> str:
    return f"{settings.media_public_base_url}/{s3_key}"


class MediaRef(BaseModel):
    url: str
    width: int
    height: int


class HeroPublic(BaseModel):
    name: str
    title: str
    subtitle: str
    photo: MediaRef | None
    cta_text: str


class AboutPublic(BaseModel):
    text: str
    photo: MediaRef | None
    credentials: list[str]


class ReviewPublic(BaseModel):
    author: str
    text: str
    child_age: int | None
    photo: MediaRef | None


class ReviewsPublic(BaseModel):
    items: list[ReviewPublic]


class PublicSite(BaseModel):
    hero: HeroPublic
    about: AboutPublic
    services: ServicesBlock
    reviews: ReviewsPublic
    faq: FaqBlock
    contacts: ContactsBlock


class SiteBlocksAdmin(BaseModel):
    hero: HeroBlock
    about: AboutBlock
    services: ServicesBlock
    reviews: ReviewsBlock
    faq: FaqBlock
    contacts: ContactsBlock
    media: list[MediaOut]  # фото, на которые ссылаются блоки
