import warnings
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image, ImageOps

from app.site_content.errors import FileTooLarge, UnsupportedImage

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_SIDE = 2000
MAX_PIXELS = 40_000_000

# Формат (по содержимому файла) -> (content type, расширение).
_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
_JPEG_QUALITY = 85


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    content_type: str
    extension: str
    width: int
    height: int


def process_image(data: bytes) -> ProcessedImage:
    """Проверяет, что байты — JPEG/PNG/WebP, и пересохраняет их без метаданных.

    Тип определяется по содержимому, а не по имени или заголовку запроса. Ориентация из EXIF
    применяется к пикселям, длинная сторона уменьшается до `MAX_SIDE`, EXIF удаляется
    (ICC-профиль остаётся). Синхронная и тяжёлая: из async-кода вызывать через поток.
    """
    image, image_format = _decode(data)
    content_type, extension = _FORMATS[image_format]

    # Первый кадр анимации; exif_transpose отдаёт обычное изображение с применённой ориентацией.
    icc_profile = image.info.get("icc_profile")
    source_mode = image.mode
    image = ImageOps.exif_transpose(image)
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    if image_format == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
        if source_mode == "CMYK":
            icc_profile = None  # профиль описывал CMYK, к RGB-пикселям он не подходит

    save_kwargs: dict[str, Any] = {}
    if icc_profile:
        save_kwargs["icc_profile"] = icc_profile
    if image_format == "JPEG":
        save_kwargs.update(quality=_JPEG_QUALITY, optimize=True)
    buffer = BytesIO()
    image.save(buffer, format=image_format, **save_kwargs)
    return ProcessedImage(
        data=buffer.getvalue(),
        content_type=content_type,
        extension=extension,
        width=image.width,
        height=image.height,
    )


def _decode(data: bytes) -> tuple[Image.Image, str]:
    """Открывает и полностью разбирает изображение; всё подозрительное — в ошибки API."""
    try:
        with warnings.catch_warnings():
            # Pillow предупреждает о слишком больших картинках (decompression bomb).
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(BytesIO(data))
            image_format = image.format
            if image_format not in _FORMATS:
                raise UnsupportedImage
            if image.width * image.height > MAX_PIXELS:
                raise FileTooLarge
            image.load()  # обрезанный или битый файл падает здесь
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise FileTooLarge from exc
    except (UnsupportedImage, FileTooLarge):
        raise
    except Exception as exc:  # Pillow на битых файлах бросает самые разные исключения
        raise UnsupportedImage from exc
    return image, image_format
