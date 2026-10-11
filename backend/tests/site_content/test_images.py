import warnings
from io import BytesIO

import pytest
from PIL import Image

from app.site_content.errors import FileTooLarge, UnsupportedImage
from app.site_content.images import process_image
from tests.site_content.conftest import make_image


def test_jpeg_exif_is_stripped_and_orientation_applied() -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: повернуть на 90°
    exif[0x8825] = {2: (55.0, 45.0, 0.0)}  # GPSInfo
    out = process_image(make_image("JPEG", (300, 200), exif=exif))
    assert (out.width, out.height) == (200, 300)
    assert out.content_type == "image/jpeg"
    assert out.extension == "jpg"
    assert len(Image.open(BytesIO(out.data)).getexif()) == 0


def test_long_side_is_reduced_to_2000() -> None:
    out = process_image(make_image("PNG", (4000, 1000)))
    assert (out.width, out.height, out.content_type) == (2000, 500, "image/png")
    assert out.extension == "png"


def test_small_image_is_not_upscaled() -> None:
    out = process_image(make_image("WEBP", (640, 480)))
    assert (out.width, out.height, out.extension) == (640, 480, "webp")
    assert out.content_type == "image/webp"


def test_rgba_png_keeps_transparency() -> None:
    out = process_image(make_image("PNG", (20, 20), mode="RGBA"))
    assert Image.open(BytesIO(out.data)).mode == "RGBA"


def test_cmyk_jpeg_is_converted_to_rgb() -> None:
    out = process_image(make_image("JPEG", (20, 20), mode="CMYK"))
    assert Image.open(BytesIO(out.data)).mode == "RGB"


def test_animated_webp_keeps_first_frame_only() -> None:
    frames = [Image.new("RGB", (30, 20), color) for color in ("red", "blue")]
    buffer = BytesIO()
    frames[0].save(buffer, format="WEBP", save_all=True, append_images=frames[1:], duration=100)
    out = process_image(buffer.getvalue())
    assert getattr(Image.open(BytesIO(out.data)), "n_frames", 1) == 1


@pytest.mark.parametrize(
    "payload",
    [
        b"<html><script>alert(1)</script></html>",
        b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
        b"",
        make_image("GIF", (10, 10)),
        make_image("JPEG", (100, 100))[:200],
    ],
    ids=["html", "svg", "empty", "gif", "truncated_jpeg"],
)
def test_rejects_non_allowed_or_broken_files(payload: bytes) -> None:
    with pytest.raises(UnsupportedImage):
        process_image(payload)


def test_rejects_decompression_bomb() -> None:
    bomb = make_image("PNG", (7000, 7000), mode="1")  # 49 Мп, файл маленький
    assert len(bomb) < 1024 * 1024
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # предупреждение Pillow не должно утекать наружу
        with pytest.raises(FileTooLarge):
            process_image(bomb)
