"""Turns an uploaded file into the images NOVA stores and serves.

Nothing a client uploads is stored as sent. Every file is decoded with Pillow
and re-encoded, which does three jobs at once:

  - It proves the file is an image. A file that only *claims* to be one (a
    renamed HTML page, a polyglot) fails to decode and is refused; what is
    stored is always pixels NOVA encoded itself.
  - It drops metadata. Phone photos carry EXIF, often including the GPS
    position where they were taken — a salon owner's home, not the salon.
  - It sizes the image for the web: a `large` variant for the storefront and a
    `thumb` for search cards, both WebP.

Decompression bombs — a small file that decodes to billions of pixels — are
refused before decoding, by checking the declared size against a pixel cap.
"""

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.exceptions import ValidationDomainError

#: Formats accepted on upload. What is stored is always WebP.
ACCEPTED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
#: 40 megapixels: comfortably above any phone camera, far below a bomb.
MAX_PIXELS = 40_000_000
#: Longest edge of each stored variant, in pixels.
VARIANT_SIZES = {"large": 1600, "thumb": 480}
WEBP_QUALITY = 82


class InvalidImageError(ValidationDomainError):
    code = "invalid_image"


@dataclass(frozen=True)
class Variant:
    data: bytes
    width: int
    height: int


@dataclass(frozen=True)
class ProcessedImage:
    """Every stored variant, and the dimensions of the largest."""

    variants: dict[str, Variant]

    @property
    def width(self) -> int:
        return self.variants["large"].width

    @property
    def height(self) -> int:
        return self.variants["large"].height


def process_upload(data: bytes) -> ProcessedImage:
    """Decodes `data`, and returns freshly encoded WebP variants of it."""
    if not data:
        raise InvalidImageError("The file is empty.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ACCEPTED_FORMATS:
                raise InvalidImageError("Upload a JPEG, PNG or WebP image.")
            if probe.width * probe.height > MAX_PIXELS:
                raise InvalidImageError("That image is too large. Use one under 40 megapixels.")
            # `load()` actually decodes; `open()` only read the header.
            probe.load()
            image = ImageOps.exif_transpose(probe)
            image = image.convert("RGBA" if _has_alpha(image) else "RGB")
    except InvalidImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise InvalidImageError("That file is not a readable image.") from exc

    variants = {name: _encode(image, edge) for name, edge in VARIANT_SIZES.items()}
    return ProcessedImage(variants=variants)


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info)


def _encode(image: Image.Image, longest_edge: int) -> Variant:
    copy = image.copy()
    copy.thumbnail((longest_edge, longest_edge), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    # A fresh encode carries no EXIF/XMP/ICC chunks unless passed explicitly.
    copy.save(out, format="WEBP", quality=WEBP_QUALITY, method=4)
    return Variant(data=out.getvalue(), width=copy.width, height=copy.height)
