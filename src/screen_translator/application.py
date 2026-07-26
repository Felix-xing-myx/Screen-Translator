"""Application composition entry point."""

from __future__ import annotations

import sys
import ctypes
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .ocr import configure_tesseract

from .ui.main_window import MainWindow


def _configure_windows_identity() -> None:
    """Give Windows a stable taskbar identity when running from Python too."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ScreenTranslator.Desktop"
        )
    except (AttributeError, OSError, TypeError):
        pass


def main() -> int:
    _configure_windows_identity()
    configure_tesseract()
    app = QApplication(sys.argv)
    app.setApplicationName("ScreenTranslator")
    instance_lock = QLockFile(
        str(Path(tempfile.gettempdir()) / "ScreenTranslator.instance.lock")
    )
    if not instance_lock.tryLock(100):
        return 0

    icon_path = Path(__file__).resolve().parent / "assets" / "screen_translator.ico"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    return app.exec()
