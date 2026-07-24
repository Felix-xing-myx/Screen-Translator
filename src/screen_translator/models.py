"""Domain models shared by the application and future integrations."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect


@dataclass
class MonitorRegion:
    rect: QRect
    enabled: bool = True
    last_text: str = ""
    translated: str = ""

