"""What an upload becomes before it is stored. Pure — no database."""

import io

import pytest
from PIL import Image

from app.integrations.images import (
    VARIANT_SIZES,
    InvalidImageError,
    process_upload,
)


def _jpeg_with_gps(size: tuple[int, int] = (3000, 2000)) -> bytes:
    """A phone-style JPEG carrying a GPS position in its EXIF."""
    image = Image.new("RGB", size, (200, 120, 90))
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (24.0, 42.0, 49.0), 3: "E", 4: (46.0, 40.0, 31.0)}  # GPSInfo
    exif[0x010F] = "PhoneMaker"  # Make
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def _png(size: tuple[int, int], mode: str = "RGBA") -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, (0, 0, 0, 0) if mode == "RGBA" else 0).save(out, format="PNG")
    return out.getvalue()


def test_every_variant_is_webp_within_its_size() -> None:
    processed = process_upload(_jpeg_with_gps())

    for name, edge in VARIANT_SIZES.items():
        variant = processed.variants[name]
        with Image.open(io.BytesIO(variant.data)) as image:
            assert image.format == "WEBP"
            assert max(image.size) <= edge
            assert image.size == (variant.width, variant.height)
    assert (processed.width, processed.height) == (1600, 1067)


def test_location_and_camera_metadata_are_gone() -> None:
    """A salon photo taken at home must not publish home's coordinates."""
    processed = process_upload(_jpeg_with_gps())

    for variant in processed.variants.values():
        with Image.open(io.BytesIO(variant.data)) as image:
            assert not image.getexif()
            assert "exif" not in image.info


def test_a_small_image_is_not_blown_up() -> None:
    processed = process_upload(_png((300, 200)))

    assert (processed.width, processed.height) == (300, 200)


def test_transparency_survives() -> None:
    processed = process_upload(_png((40, 40)))

    with Image.open(io.BytesIO(processed.variants["large"].data)) as image:
        assert image.mode == "RGBA"


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"<html><script>alert(1)</script></html>",
        b"GIF89a" + b"\x00" * 64,  # a real image format, but not an accepted one
        _png((40, 40))[:30],  # truncated
    ],
)
def test_anything_that_is_not_an_accepted_image_is_refused(data: bytes) -> None:
    with pytest.raises(InvalidImageError):
        process_upload(data)


def test_a_decompression_bomb_is_refused_before_decoding() -> None:
    """A tiny PNG that claims 60 megapixels."""
    bomb = _png((10_000, 6_000), mode="L")
    assert len(bomb) < 200_000

    with pytest.raises(InvalidImageError, match="too large"):
        process_upload(bomb)
