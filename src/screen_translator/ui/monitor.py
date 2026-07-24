"""Dialogs for configuring continuous screen monitoring."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class MonitorSetupDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("持续监控设置")
        self.setMinimumWidth(460)

        self.scope_combo = QComboBox()
        self.scope_combo.addItem("监控指定区域", "region")
        self.scope_combo.addItem("监控主显示器全屏", "full")
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.5, 60.0)
        self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setValue(2.0)
        self.interval_spin.setSuffix(" 秒")

        form = QFormLayout()
        form.addRow("监控范围：", self.scope_combo)
        form.addRow("扫描间隔：", self.interval_spin)
        note = QLabel(
            "指定区域模式可以一次选择多个游戏字幕或固定文本区域。程序只会在某个区域的 OCR 结果变化时重新请求翻译。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    @property
    def monitor_full_screen(self) -> bool:
        return self.scope_combo.currentData() == "full"

    @property
    def interval_seconds(self) -> float:
        return self.interval_spin.value()
