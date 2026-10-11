import pytest
from pydantic import ValidationError
from uuid_utils.compat import uuid7

from app.site_content.models import BlockKey
from app.site_content.schemas import (
    BLOCK_SCHEMAS,
    AboutBlock,
    ContactsBlock,
    FaqBlock,
    FaqItem,
    HeroBlock,
    ReviewItem,
    ReviewsBlock,
    ServiceItem,
    ServicesBlock,
    referenced_media_ids,
)


def _service(**overrides: object) -> ServiceItem:
    values: dict[str, object] = {
        "title": "Урок",
        "description": "",
        "duration_min": 60,
        "price_rub": 1500,
        "format": "Онлайн",
    }
    return ServiceItem.model_validate({**values, **overrides})


def test_hero_strips_whitespace_and_rejects_blank_title() -> None:
    hero = HeroBlock(name="  Анна  ", title="Т", subtitle="С", cta_text="Записаться")
    assert hero.name == "Анна"
    with pytest.raises(ValidationError):
        HeroBlock(name="Анна", title="   ", subtitle="С", cta_text="Записаться")


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        FaqItem.model_validate({"question": "В?", "answer": "О", "extra": "x"})


def test_block_schemas_cover_every_key() -> None:
    assert set(BLOCK_SCHEMAS) == set(BlockKey)


@pytest.mark.parametrize(
    ("field", "value"),
    [("duration_min", 10), ("duration_min", 241), ("price_rub", -1), ("price_rub", 100_001)],
)
def test_service_item_limits(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        _service(**{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [("duration_min", 15), ("duration_min", 240), ("price_rub", 0), ("price_rub", 100_000)],
)
def test_service_item_boundaries_are_valid(field: str, value: int) -> None:
    assert getattr(_service(**{field: value}), field) == value


def test_services_at_most_20_items() -> None:
    assert len(ServicesBlock(items=[_service()] * 20).items) == 20
    with pytest.raises(ValidationError):
        ServicesBlock(items=[_service()] * 21)


def test_about_credentials_limits() -> None:
    assert len(AboutBlock(text="Т", credentials=["а"] * 20).credentials) == 20
    with pytest.raises(ValidationError):
        AboutBlock(text="Т", credentials=["а"] * 21)
    with pytest.raises(ValidationError):
        AboutBlock(text="Т", credentials=["   "])


def test_reviews_and_faq_item_limits() -> None:
    review = ReviewItem(author="А", text="Т")
    assert len(ReviewsBlock(items=[review] * 30).items) == 30
    with pytest.raises(ValidationError):
        ReviewsBlock(items=[review] * 31)
    faq = FaqItem(question="В", answer="О")
    assert len(FaqBlock(items=[faq] * 30).items) == 30
    with pytest.raises(ValidationError):
        FaqBlock(items=[faq] * 31)


@pytest.mark.parametrize(
    ("age", "ok"), [(2, False), (3, True), (18, True), (19, False), (None, True)]
)
def test_review_child_age_range(age: int | None, ok: bool) -> None:
    if ok:
        assert ReviewItem(author="А", text="Т", child_age=age).child_age == age
    else:
        with pytest.raises(ValidationError):
            ReviewItem(author="А", text="Т", child_age=age)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@anna_english", "anna_english"),
        ("https://t.me/anna_english", "anna_english"),
        ("http://t.me/anna_english", "anna_english"),
        ("t.me/anna_english", "anna_english"),
        ("  @anna_english  ", "anna_english"),
        ("", None),
        ("   ", None),
    ],
)
def test_contacts_normalizes_telegram(raw: str, expected: str | None) -> None:
    assert ContactsBlock(telegram=raw).telegram == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8 (999) 123-45-67", "+79991234567"),
        ("+7 999 123 45 67", "+79991234567"),
        ("+44 20 7946 0958", "+442079460958"),
        ("79991234567", "+79991234567"),
        ("999 123-45-67", "+79991234567"),
        ("9991234567", "+79991234567"),
        ("(999) 123-45-67", "+79991234567"),
    ],
)
def test_contacts_normalizes_phone_and_whatsapp(raw: str, expected: str) -> None:
    contacts = ContactsBlock(phone=raw, whatsapp=raw)
    assert contacts.phone == expected
    assert contacts.whatsapp == expected


def test_contacts_blank_values_become_none() -> None:
    contacts = ContactsBlock(phone=" ", whatsapp="", email="  ", working_hours_text="")
    assert contacts == ContactsBlock()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("telegram", "ann", "Укажите имя пользователя Telegram, например @anna_english"),
        ("telegram", "anna english", "Укажите имя пользователя Telegram, например @anna_english"),
        ("phone", "12345", "Укажите телефон в формате"),
        ("phone", "4951234567", "Укажите телефон в формате"),
        ("whatsapp", "495 123-45-67", "Укажите телефон в формате"),
        ("phone", "+٧٩٩٩١٢٣٤٥٦٧", "Укажите телефон в формате"),
        ("phone", "٩٩٩١٢٣٤٥٦٧", "Укажите телефон в формате"),
        ("telegram", "anna_englis٣", "Укажите имя пользователя Telegram"),
        ("whatsapp", "abc", "Укажите телефон в формате"),
        ("email", "not-an-email", "email"),
    ],
)
def test_contacts_rejects_invalid(field: str, value: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        ContactsBlock.model_validate({field: value})


def test_referenced_media_ids_reports_paths() -> None:
    a, b = uuid7(), uuid7()
    reviews = ReviewsBlock(
        items=[ReviewItem(author="А", text="Т"), ReviewItem(author="Б", text="Т", photo_media_id=a)]
    )
    assert referenced_media_ids(reviews) == [(("items", 1, "photo_media_id"), a)]
    hero = HeroBlock(name="А", title="Т", subtitle="С", cta_text="К", photo_media_id=b)
    assert referenced_media_ids(hero) == [(("photo_media_id",), b)]
    about = AboutBlock(text="Т", credentials=[], photo_media_id=a)
    assert referenced_media_ids(about) == [(("photo_media_id",), a)]


def test_referenced_media_ids_skips_none_and_other_blocks() -> None:
    hero = HeroBlock(name="А", title="Т", subtitle="С", cta_text="К")
    assert referenced_media_ids(hero) == []
    assert referenced_media_ids(FaqBlock(items=[])) == []
