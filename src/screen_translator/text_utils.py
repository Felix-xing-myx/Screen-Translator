"""Text normalization helpers shared by UI and services."""

from __future__ import annotations

import re


def compact_display_text(text: str) -> str:
    """压缩译文中的多余换行、制表符和连续空格，提升阅读密度。"""
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()
