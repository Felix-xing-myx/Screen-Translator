"""Application settings dialog."""

from __future__ import annotations

import csv
import io
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..audio_capture import AudioCaptureError, list_audio_devices
from ..config import AppSettings, save_settings
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

        self.audio_key_edit = QLineEdit(settings.dashscope_api_key)
        self.audio_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.audio_mode_combo = QComboBox()
        self.audio_mode_combo.addItem("系统全局声音", "global")
        self.audio_mode_combo.addItem("指定进程（含子进程）", "process")
        self.audio_mode_combo.addItem("麦克风", "microphone")
        mode_index = self.audio_mode_combo.findData(settings.audio_source_mode)
        self.audio_mode_combo.setCurrentIndex(max(0, mode_index))

        self.audio_device_combo = QComboBox()
        self.audio_device_combo.addItem("默认设备", -1)
        try:
            for device in list_audio_devices():
                self.audio_device_combo.addItem(
                    f"[{device.kind}] {device.name}", device.index
                )
        except AudioCaptureError:
            self.audio_device_combo.setToolTip("Install audio dependencies to select devices")
        device_index = self.audio_device_combo.findData(settings.audio_device_id)
        if device_index >= 0:
            self.audio_device_combo.setCurrentIndex(device_index)

        self.audio_process_combo = QComboBox()
        self.audio_process_combo.addItem("请选择进程", 0)
        for process_id, process_name in self._list_processes():
            self.audio_process_combo.addItem(
                f"{process_name} (PID {process_id})", process_id
            )
        process_index = self.audio_process_combo.findData(settings.audio_process_id)
        if process_index >= 0:
            self.audio_process_combo.setCurrentIndex(process_index)
        self.audio_children_check = QCheckBox("包含目标进程的子进程")
        self.audio_children_check.setChecked(settings.audio_include_children)
        self.audio_source_language_edit = QLineEdit(settings.audio_source_language)
        self.audio_target_language_edit = QLineEdit(settings.audio_target_language)
        self.audio_vad_mode_spin = QSpinBox()
        self.audio_vad_mode_spin.setRange(0, 3)
        self.audio_vad_mode_spin.setValue(settings.audio_vad_mode)
        self.audio_vad_post_spin = QSpinBox()
        self.audio_vad_post_spin.setRange(200, 6000)
        self.audio_vad_post_spin.setValue(settings.audio_vad_post_roll_ms)
        self.audio_history_spin = QSpinBox()
        self.audio_history_spin.setRange(1, 10)
        self.audio_history_spin.setValue(settings.audio_history_limit)

        form.addRow("阿里云 DashScope API Key：", self.audio_key_edit)
        form.addRow("音频来源：", self.audio_mode_combo)
        form.addRow("音频设备：", self.audio_device_combo)
        form.addRow("目标进程：", self.audio_process_combo)
        form.addRow("子进程：", self.audio_children_check)
        form.addRow("音频源语言：", self.audio_source_language_edit)
        form.addRow("音频目标语言：", self.audio_target_language_edit)
        form.addRow("VAD 灵敏度（0-3）：", self.audio_vad_mode_spin)
        form.addRow("句尾静音阈值（毫秒）：", self.audio_vad_post_spin)
        form.addRow("保留最近句数（最多 10）：", self.audio_history_spin)

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

    @staticmethod
    def _list_processes() -> list[tuple[int, str]]:
        try:
            output = subprocess.check_output(
                ["tasklist", "/fo", "csv", "/nh"],
                text=True,
                encoding="mbcs",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return []
        result: list[tuple[int, str]] = []
        for row in csv.reader(io.StringIO(output)):
            if len(row) < 2:
                continue
            try:
                result.append((int(row[1]), row[0]))
            except ValueError:
                continue
        return sorted(result, key=lambda item: item[1].lower())

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
        self.settings.dashscope_api_key = self.audio_key_edit.text().strip()
        self.settings.audio_source_mode = self.audio_mode_combo.currentData()
        self.settings.audio_device_id = int(self.audio_device_combo.currentData() or -1)
        self.settings.audio_process_id = int(self.audio_process_combo.currentData() or 0)
        self.settings.audio_process_name = self.audio_process_combo.currentText()
        self.settings.audio_include_children = self.audio_children_check.isChecked()
        self.settings.audio_source_language = self.audio_source_language_edit.text().strip() or "auto"
        self.settings.audio_target_language = self.audio_target_language_edit.text().strip() or "zh"
        self.settings.audio_vad_mode = self.audio_vad_mode_spin.value()
        self.settings.audio_vad_post_roll_ms = self.audio_vad_post_spin.value()
        self.settings.audio_history_limit = self.audio_history_spin.value()
        save_settings(self.settings)
        super().accept()
