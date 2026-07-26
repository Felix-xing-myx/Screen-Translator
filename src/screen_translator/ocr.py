"""OCR runtime discovery and Tesseract integration helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps


def application_root() -> Path:
    """Return the directory containing the executable or project package."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundled_tesseract_path() -> Path | None:
    """Find Tesseract in both source and packaged layouts."""
    root = application_root()
    candidates = (
        root / "tesseract" / "tesseract.exe",
        root / "vendor" / "tesseract" / "tesseract.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def configure_tesseract(configured_path: str = "") -> Path | None:
    """Configure pytesseract from a user path or the bundled runtime."""
    if configured_path.strip():
        candidate = Path(configured_path.strip())
        if candidate.is_dir():
            candidate /= "tesseract.exe"
        if candidate.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return candidate
        return None

    bundled = bundled_tesseract_path()
    if bundled:
        pytesseract.pytesseract.tesseract_cmd = str(bundled)
    return bundled


def _configure_for_ocr(configured_path: str) -> None:
    configured_path = configured_path.strip()
    if configured_path:
        candidate = Path(configured_path)
        if candidate.is_dir():
            candidate = candidate / "tesseract.exe"
        if not candidate.is_file():
            raise RuntimeError(
                f"找不到 Tesseract 可执行文件：{candidate}\n"
                "请在设置中选择 E:\\Tesseract OCR\\tesseract.exe。"
            )
        pytesseract.pytesseract.tesseract_cmd = str(candidate)
        return

    bundled_path = bundled_tesseract_path()
    if bundled_path:
        pytesseract.pytesseract.tesseract_cmd = str(bundled_path)


def _prepare_ocr_image(image: Image.Image) -> Image.Image:
    """Prepare a screenshot for the single-region OCR workflow."""
    ocr_image = ImageOps.grayscale(image.convert("RGB"))
    ocr_image = ImageOps.autocontrast(ocr_image)
    if max(ocr_image.size) < 3200:
        ocr_image = ocr_image.resize(
            (ocr_image.width * 2, ocr_image.height * 2),
            Image.Resampling.LANCZOS,
        )
    return ocr_image


def recognize_english(image: Image.Image, tesseract_path: str = "") -> str:
    """Recognize English text from one user-selected screenshot region."""
    _configure_for_ocr(tesseract_path)
    ocr_image = _prepare_ocr_image(image)

    text = pytesseract.image_to_string(
        ocr_image, lang="eng", config="--oem 3 --psm 11"
    ).strip()
    if not text:
        text = pytesseract.image_to_string(
            ocr_image, lang="eng", config="--oem 3 --psm 6"
        ).strip()
    return text
