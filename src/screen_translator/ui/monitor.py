"""Dialog for configuring manually selected continuous monitor regions."""

from __future__ import annotations

from PySide6.QtWidgets import (
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

        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.5, 60.0)
        self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setValue(2.0)
        self.interval_spin.setSuffix(" 秒")

        form = QFormLayout()
        form.addRow("扫描间隔：", self.interval_spin)
        note = QLabel(
            "开始后请框选一个或多个固定文字区域。程序只会在指定区域的 OCR 结果发生变化时重新请求翻译。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    @property
    def interval_seconds(self) -> float:
        return self.interval_spin.value()
