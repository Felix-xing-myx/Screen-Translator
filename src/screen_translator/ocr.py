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



def recognize_english(image: Image.Image, tesseract_path: str = "") -> str:
    """识别屏幕截图中的英文，集中处理路径、预处理和备用版面模式。"""
    configured_path = tesseract_path.strip()
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
    else:
        bundled_path = bundled_tesseract_path()
        if bundled_path:
            pytesseract.pytesseract.tesseract_cmd = str(bundled_path)

    # 游戏字幕和网页小字通常只有十几像素高。先放大、转灰度并增强
    # 对比度，可以显著降低“截图有字但 OCR 返回空”的情况。
    ocr_image = ImageOps.grayscale(image.convert("RGB"))
    ocr_image = ImageOps.autocontrast(ocr_image)
    if max(ocr_image.size) < 3200:
        ocr_image = ocr_image.resize(
            (ocr_image.width * 2, ocr_image.height * 2),
            Image.Resampling.LANCZOS,
        )

    # psm 11 适合屏幕上分散的字幕、按钮和多行文本；如果当前画面
    # 更像一个完整段落，再用 psm 6 做一次备用识别。
    text = pytesseract.image_to_string(
        ocr_image, lang="eng", config="--oem 3 --psm 11"
    ).strip()
    if not text:
        text = pytesseract.image_to_string(
            ocr_image, lang="eng", config="--oem 3 --psm 6"
        ).strip()
    return text
