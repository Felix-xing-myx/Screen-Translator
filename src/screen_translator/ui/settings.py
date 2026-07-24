"""Application settings dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import AppSettings
from ..hotkeys import HotkeyEdit


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(560)
        self.settings = settings

        self.url_edit = QLineEdit(settings.translation_url)
        self.key_edit = QLineEdit(settings.translation_api_key)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.hotkey_edit = HotkeyEdit(settings.hotkey)
        self.tesseract_edit = QLineEdit(settings.tesseract_path)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self.browse_tesseract)
        tesseract_row = QWidget()
        tesseract_layout = QVBoxLayout(tesseract_row)
        tesseract_layout.setContentsMargins(0, 0, 0, 0)
        tesseract_layout.addWidget(self.tesseract_edit)
        tesseract_layout.addWidget(browse)

        form = QFormLayout()
        form.addRow("全局热键：", self.hotkey_edit)
        form.addRow("翻译接口地址：", self.url_edit)
        form.addRow("API key（可选）：", self.key_edit)
        form.addRow("Tesseract 路径：", tesseract_row)

        note = QLabel(
            "热键至少需要包含 Ctrl、Alt、Shift 或 Windows 键中的一个；保存后立即生效。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def browse_tesseract(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 tesseract.exe", "", "Executable (*.exe)")
        if path:
            self.tesseract_edit.setText(path)

    def accept(self) -> None:
        hotkey = self.hotkey_edit.text().strip()
        if not hotkey:
            QMessageBox.warning(self, "设置", "请录入一个全局热键。")
            return
        self.settings.hotkey = hotkey
        self.settings.translation_url = self.url_edit.text().strip()
        self.settings.translation_api_key = self.key_edit.text().strip()
        self.settings.tesseract_path = self.tesseract_edit.text().strip()
        save_settings(self.settings)
        super().accept()
