"""Helpers for preparing screenshots before OCR."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from PIL import Image, ImageDraw
from PySide6.QtCore import QRect


def image_fingerprint(image: Image.Image) -> bytes:
    """Return a cheap, low-resolution fingerprint for change detection."""
    thumbnail = image.convert("L").resize((32, 32), Image.Resampling.BILINEAR)
    quantized = bytes(value // 16 for value in thumbnail.getdata())
    return hashlib.blake2b(quantized, digest_size=8).digest()


def mask_excluded_regions(
    image: Image.Image,
    capture_rect: QRect,
    excluded_rects: Iterable[QRect],
    fill: tuple[int, int, int] = (0, 0, 0),
) -> Image.Image:
    """Mask screen rectangles that must not be sent to OCR.

    ``capture_rect`` and ``excluded_rects`` use the same logical screen
    coordinate system as Qt.  The image can have a different pixel density
    (for example on a Windows display scaled to 125%), so the mapping is
    derived from the actual image dimensions instead of assuming 1:1 pixels.
    The image is modified in place and returned for convenient use in the
    capture pipeline.
    """

    if image.width <= 0 or image.height <= 0 or capture_rect.isEmpty():
        return image

    scale_x = image.width / capture_rect.width()
    scale_y = image.height / capture_rect.height()
    draw = ImageDraw.Draw(image)
    for excluded in excluded_rects:
        overlap = capture_rect.intersected(excluded)
        if overlap.isEmpty():
            continue

        left = max(0, round((overlap.left() - capture_rect.left()) * scale_x))
        top = max(0, round((overlap.top() - capture_rect.top()) * scale_y))
        right = min(
            image.width - 1,
            round((overlap.right() + 1 - capture_rect.left()) * scale_x) - 1,
        )
        bottom = min(
            image.height - 1,
            round((overlap.bottom() + 1 - capture_rect.top()) * scale_y) - 1,
        )
        if left <= right and top <= bottom:
            draw.rectangle((left, top, right, bottom), fill=fill)
    return image
