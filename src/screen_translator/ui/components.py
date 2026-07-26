"""Small reusable widgets for the application workbench."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class SectionCard(QFrame):
    """A themed card with an optional eyebrow, title and subtitle."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        *,
        object_name: str = "sectionCard",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.body_layout = QVBoxLayout(self)
        self.body_layout.setContentsMargins(16, 14, 16, 16)
        self.body_layout.setSpacing(9)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("sectionTitle")
        self.body_layout.addWidget(self.title_label)
        self.section_rule = QFrame()
        self.section_rule.setObjectName("sectionRule")
        self.section_rule.setFrameShape(QFrame.Shape.HLine)
        self.section_rule.setFixedHeight(1)
        self.body_layout.addWidget(self.section_rule)
        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setObjectName("sectionSubtitle")
            self.subtitle_label.setWordWrap(True)
            self.body_layout.addWidget(self.subtitle_label)
        else:
            self.subtitle_label = None

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self.body_layout.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self.body_layout.addLayout(layout, stretch)


class ActionButton(QPushButton):
    """A button that exposes semantic visual roles through QSS properties."""

    def __init__(
        self,
        text: str,
        *,
        role: str = "secondary",
        parent: QWidget | None = None,
    ):
        super().__init__(text, parent)
        self.setProperty("role", role)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover_shadow = QGraphicsDropShadowEffect(self)
        self._hover_shadow.setOffset(0, 0)
        self._hover_shadow.setBlurRadius(0)
        # Keep the interaction cue understated: C4 uses a crisp border change
        # with only a small halo instead of a large neon glow.
        self._hover_shadow.setColor(QColor(107, 216, 255, 60))
        self.setGraphicsEffect(self._hover_shadow)
        self._hover_animation = QPropertyAnimation(self._hover_shadow, b"blurRadius", self)
        self._hover_animation.setDuration(170)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _animate_hover(self, target: float) -> None:
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover_shadow.blurRadius())
        self._hover_animation.setEndValue(target)
        self._hover_animation.start()

    def enterEvent(self, event) -> None:
        if self.isEnabled():
            self.setProperty("hovered", True)
            self.style().unpolish(self)
            self.style().polish(self)
            self._animate_hover(5 if self.property("role") == "primary" else 3)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setProperty("hovered", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self._animate_hover(0)
        super().leaveEvent(event)


class SliderRow(QWidget):
    """A labeled slider with a persistent value readout."""

    value_changed = Signal(int)

    def __init__(
        self,
        label: str,
        minimum: int,
        maximum: int,
        value: int,
        suffix: str = "%",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(value)
        self.value_label = QLabel()
        self.value_label.setObjectName("microLabel")
        self._suffix = suffix
        self._label = QLabel(label)
        self._label.setObjectName("hintLabel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._label)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.value_label)
        self.slider.valueChanged.connect(self._update_value)
        self.slider.valueChanged.connect(self.value_changed)
        self._update_value(self.slider.value())

    def _update_value(self, value: int) -> None:
        self.value_label.setText(f"{value}{self._suffix}")

    def value(self) -> int:
        return self.slider.value()

    def set_value(self, value: int) -> None:
        self.slider.setValue(value)


class StatusBadge(QLabel):
    """Compact status label with a semantic state property."""

    def __init__(self, text: str = "准备就绪", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("statusBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_state("idle")

    def set_state(self, state: str) -> None:
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)
