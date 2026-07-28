"""Small, thread-safe runtime counters used by the main window."""

from __future__ import annotations

import os
from dataclasses import dataclass
from threading import Lock

try:  # pragma: no cover - availability depends on the runtime environment
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


@dataclass(frozen=True)
class PerformanceSnapshot:
    cpu_percent: float | None
    ocr_count: int
    translation_count: int


class PerformanceStats:
    """Collect counters without making worker threads depend on Qt widgets."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._ocr_count = 0
        self._translation_count = 0
        self._process = psutil.Process(os.getpid()) if psutil is not None else None
        if self._process is not None:
            self._process.cpu_percent(None)

    def record_ocr(self) -> None:
        with self._lock:
            self._ocr_count += 1

    def record_translation(self) -> None:
        with self._lock:
            self._translation_count += 1

    def snapshot(self) -> PerformanceSnapshot:
        with self._lock:
            ocr_count = self._ocr_count
            translation_count = self._translation_count
        cpu_percent = (
            None if self._process is None else float(self._process.cpu_percent(None))
        )
        return PerformanceSnapshot(cpu_percent, ocr_count, translation_count)
