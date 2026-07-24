"""Application composition entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ocr import configure_tesseract

from .ui.main_window import MainWindow


def main() -> int:
    configure_tesseract()
    app = QApplication(sys.argv)
    app.setApplicationName("ScreenTranslator")
    window = MainWindow()
    window.show()
    return app.exec()

