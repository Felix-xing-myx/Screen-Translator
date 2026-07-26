"""Text normalization helpers shared by UI and services."""

from __future__ import annotations

import re


def compact_display_text(text: str, *, preserve_lines: bool = False) -> str:
    """Normalize display whitespace while optionally retaining result lines."""
    normalized = text.replace("\u00a0", " ")
    if not preserve_lines:
        return re.sub(r"\s+", " ", normalized).strip()

    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in normalized.splitlines()]
    return "\n".join(line for line in lines if line)
