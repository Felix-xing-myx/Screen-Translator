"""Background workers that connect OCR and translation services to Qt."""

from __future__ import annotations

import requests
import pytesseract
from PIL import Image
from PySide6.QtCore import QThread, Signal

from .config import AppSettings
from .ocr import recognize_english
from .translator import translate_text


class TranslationWorker(QThread):
    completed = Signal(str, str)
    failed = Signal(str)
    no_text = Signal()
    unchanged = Signal(str)

    def __init__(self, image: Image.Image, settings: AppSettings, skip_text: str = ""):
        super().__init__()
        self.image = image
        self.settings = settings
        self.skip_text = skip_text

    def run(self) -> None:
        try:
            text = recognize_english(self.image, self.settings.tesseract_path)
            if not text:
                self.no_text.emit()
                return
            if self.skip_text and text == self.skip_text:
                self.unchanged.emit(text)
                return

            translated = translate_text(text, self.settings)
            self.completed.emit(text, translated)
        except pytesseract.TesseractNotFoundError:
            self.failed.emit("找不到 Tesseract。请安装 Tesseract，或在设置中填写 tesseract.exe 的完整路径。")
        except requests.RequestException as exc:
            self.failed.emit(f"翻译请求失败：{exc}")
        except Exception as exc:  # noqa: BLE001 - 将第三方错误展示给用户
            self.failed.emit(str(exc))
