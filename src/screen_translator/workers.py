"""Background worker that connects OCR and translation services to Qt."""

from __future__ import annotations

import requests
import pytesseract
from PIL import Image
from PySide6.QtCore import QThread, Signal

from .config import AppSettings
from .languages import tesseract_language_for_source
from .ocr import recognize_text
from .performance import PerformanceStats
from .translator import translate_text


class TranslationWorker(QThread):
    completed = Signal(str, str)
    failed = Signal(str)
    no_text = Signal()
    unchanged = Signal(str)

    def __init__(
        self,
        image: Image.Image,
        settings: AppSettings,
        skip_text: str = "",
        stats: PerformanceStats | None = None,
    ):
        super().__init__()
        self.image = image
        self.settings = settings
        self.skip_text = skip_text
        self.stats = stats

    def stop(self) -> None:
        """Request a graceful stop before the next blocking stage."""
        self.requestInterruption()

    def run(self) -> None:
        try:
            if self.isInterruptionRequested():
                return
            if self.stats is not None:
                self.stats.record_ocr()
            text = recognize_text(
                self.image,
                self.settings.tesseract_path,
                tesseract_language_for_source(self.settings.source_language),
            )
            if self.isInterruptionRequested():
                return
            if not text:
                self.no_text.emit()
                return
            if self.skip_text and text == self.skip_text:
                self.unchanged.emit(text)
                return

            if self.stats is not None:
                self.stats.record_translation()
            translated = translate_text(text, self.settings)
            if self.isInterruptionRequested():
                return
            self.completed.emit(text, translated)
        except pytesseract.TesseractNotFoundError:
            if self.isInterruptionRequested():
                return
            self.failed.emit(
                "找不到 Tesseract。请安装 Tesseract，或在设置中填写 tesseract.exe 的完整路径。"
            )
        except requests.RequestException as exc:
            if self.isInterruptionRequested():
                return
            self.failed.emit(f"翻译请求失败：{exc}")
        except Exception as exc:  # noqa: BLE001 - 将第三方错误展示给用户
            if self.isInterruptionRequested():
                return
            self.failed.emit(str(exc))
