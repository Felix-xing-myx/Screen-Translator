"""Floating real-time audio translation result window."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QEvent, QPoint, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..config import AppSettings


class AudioTitleBar(QWidget):
    def __init__(self, window: "AudioTranslationWindow"):
        super().__init__(window)
        self.setObjectName("audioTitleBar")
        self.setFixedHeight(28)
        self.title_label = QLabel("Audio Translator")
        self.title_label.setObjectName("audioTitle")
        self.lock_label = QLabel()
        self.lock_label.setObjectName("audioLockState")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.addWidget(self.title_label)
        layout.addStretch(1)
        layout.addWidget(self.lock_label)

    def set_locked(self, locked: bool) -> None:
        self.lock_label.setText("LOCKED" if locked else "")


class AudioTranslationWindow(QDialog):
    """Compact translucent overlay for current and recent audio translations."""

    stop_requested = Signal()
    lock_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.locked = False
        self.drag_origin: QPoint | None = None
        self.drag_start: QPoint | None = None
        self._history_limit = 10
        self._history_cards: list[QFrame] = []

        self.setWindowTitle("音频实时翻译")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFixedSize(560, 430)

        self.card = QWidget(self)
        self.card.setObjectName("audioCard")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.card.setGraphicsEffect(shadow)
        self.card_shadow = shadow

        self.title_bar = AudioTitleBar(self)
        self.state_label = QLabel("未启动")
        self.state_label.setObjectName("audioState")
        self.speech_label = QLabel("语音状态：静音")
        self.speech_label.setObjectName("audioSpeech")
        self.source_label = QLabel("音频源：未连接")
        self.source_label.setObjectName("audioSource")
        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setValue(0)
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedHeight(6)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(4, 0, 4, 0)
        status_row.addWidget(self.state_label, 1)
        status_row.addWidget(self.speech_label)

        self.current_original = self._make_text_edit(
            "检测到声音后显示原文", "audioCurrentOriginal"
        )
        self.current_translation = self._make_text_edit(
            "翻译结果将在这里显示", "audioCurrentTranslation"
        )
        self.current_original.setFixedHeight(48)
        self.current_translation.setFixedHeight(62)

        current_panel = QFrame()
        current_panel.setObjectName("audioCurrentMask")
        current_layout = QVBoxLayout(current_panel)
        current_layout.setContentsMargins(10, 7, 10, 8)
        current_layout.setSpacing(2)
        for caption, edit in (
            ("原文", self.current_original),
            ("当前译文", self.current_translation),
        ):
            label = QLabel(caption)
            label.setObjectName("audioCurrentCaption")
            current_layout.addWidget(label)
            current_layout.addWidget(edit)

        history_label = QLabel("最近记录（最多 10 句）")
        history_label.setObjectName("audioSectionTitle")
        self.history_content = QWidget()
        self.history_content.setObjectName("audioHistoryContent")
        self.history_content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.history_content.setAutoFillBackground(False)
        self.history_content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self.history_layout = QVBoxLayout(self.history_content)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(5)
        self.history_layout.addStretch(1)
        self.history_scroll = QScrollArea()
        self.history_scroll.setObjectName("audioHistoryScroll")
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setWidget(self.history_content)
        self.history_scroll.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.history_scroll.setAutoFillBackground(False)
        self.history_scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.history_scroll.viewport().setAutoFillBackground(False)
        self.history_scroll.viewport().setStyleSheet("background: transparent; border: none;")
        self.history_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.history_scroll.setMinimumHeight(118)
        self.history_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(8, 7, 8, 8)
        card_layout.setSpacing(5)
        card_layout.addWidget(self.title_bar)
        card_layout.addLayout(status_row)
        card_layout.addWidget(self.source_label)
        card_layout.addWidget(self.level_bar)
        card_layout.addWidget(current_panel)
        card_layout.addWidget(history_label)
        card_layout.addWidget(self.history_scroll, 1)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.addWidget(self.card)

        self.background_opacity = 82
        self.text_opacity = 100
        self.mask_opacity = 45
        self.apply_visual_style()

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    @staticmethod
    def _make_text_edit(placeholder: str, object_name: str) -> QPlainTextEdit:
        edit = QPlainTextEdit()
        edit.setObjectName(object_name)
        edit.setReadOnly(True)
        edit.setPlaceholderText(placeholder)
        edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return edit

    def set_history_limit(self, value: int) -> None:
        self._history_limit = max(1, min(10, int(value)))
        while len(self._history_cards) > self._history_limit:
            self._remove_oldest_card()

    def set_state(self, state: str) -> None:
        self.state_label.setText(state)

    def set_source(self, source: str) -> None:
        self.source_label.setText(f"音频源：{source}")

    def set_level(self, value: int) -> None:
        self.level_bar.setValue(max(0, min(100, int(value))))

    def set_speech_state(self, active: bool) -> None:
        self.speech_label.setText("语音状态：检测到声音" if active else "语音状态：静音")

    def update_partial(self, original: str, translated: str) -> None:
        self.current_original.setPlainText(original)
        self.current_translation.setPlainText(translated)

    def append_result(self, original: str, translated: str) -> None:
        if not original and not translated:
            return
        self.current_original.setPlainText(original)
        self.current_translation.setPlainText(translated)
        while len(self._history_cards) >= self._history_limit:
            self._remove_oldest_card()

        card = QFrame()
        card.setObjectName("audioHistoryCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(9, 6, 9, 6)
        card_layout.setSpacing(2)
        original_label = QLabel(original or "（无原文）")
        original_label.setObjectName("audioHistoryOriginal")
        original_label.setWordWrap(True)
        original_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        translation_label = QLabel(translated or "（无译文）")
        translation_label.setObjectName("audioHistoryTranslation")
        translation_label.setWordWrap(True)
        translation_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        card_layout.addWidget(original_label)
        card_layout.addWidget(translation_label)
        self.history_layout.insertWidget(len(self._history_cards), card)
        self._history_cards.append(card)
        QTimer.singleShot(0, self._scroll_history_to_bottom)

    def _remove_oldest_card(self) -> None:
        if not self._history_cards:
            return
        card = self._history_cards.pop(0)
        self.history_layout.removeWidget(card)
        card.deleteLater()

    def _scroll_history_to_bottom(self) -> None:
        self.history_scroll.verticalScrollBar().setValue(
            self.history_scroll.verticalScrollBar().maximum()
        )

    def clear(self) -> None:
        self.current_original.clear()
        self.current_translation.clear()
        while self._history_cards:
            self._remove_oldest_card()
        self.set_level(0)
        self.set_speech_state(False)

    def set_background_opacity(self, percentage: int) -> None:
        self.background_opacity = max(0, min(100, int(percentage)))
        self.apply_visual_style()

    def set_text_opacity(self, percentage: int) -> None:
        self.text_opacity = max(30, min(100, int(percentage)))
        self.apply_visual_style()

    def set_mask_opacity(self, percentage: int) -> None:
        self.mask_opacity = max(0, min(100, int(percentage)))
        self.apply_visual_style()

    def apply_visual_style(self) -> None:
        bg = round(255 * self.background_opacity / 100)
        history_bg = round(165 * self.background_opacity / 100)
        text = round(255 * self.text_opacity / 100)
        mask = round(255 * self.mask_opacity / 100)
        chrome = round(255 * self.background_opacity / 100)
        border = round(150 * self.background_opacity / 100)
        self.setWindowOpacity(1.0)
        self.card_shadow.setColor(QColor(0, 0, 0, round(150 * self.background_opacity / 100)))
        self.setStyleSheet(
            f"QWidget#audioCard {{ background: rgba(20,25,38,{bg}); "
            f"border: 1px solid rgba(120,180,255,{border}); border-radius: 16px; }}"
            "QWidget#audioTitleBar { background: transparent; }"
            f"QLabel#audioTitle {{ color: rgba(219,234,254,{chrome}); font-size: 12px; font-weight: 600; }}"
            f"QLabel#audioLockState {{ color: rgba(125,211,252,{chrome}); font-size: 10px; font-weight: 700; }}"
            f"QLabel#audioState, QLabel#audioSource, QLabel#audioSpeech {{ color: rgba(219,234,254,{text}); }}"
            f"QLabel#audioSectionTitle, QLabel#audioCurrentCaption {{ color: rgba(125,211,252,{text}); font-weight: 600; }}"
            f"QFrame#audioCurrentMask {{ background: rgba(15,23,42,{mask}); border-radius: 10px; }}"
            f"QPlainTextEdit#audioCurrentOriginal {{ color: rgba(248,250,252,{text}); font-size: 13px; background: transparent; border: none; padding: 1px; }}"
            f"QPlainTextEdit#audioCurrentTranslation {{ color: rgba(248,250,252,{text}); font-size: 16px; font-weight: 600; background: transparent; border: none; padding: 1px; }}"
            f"QFrame#audioHistoryCard {{ background: rgba(15,23,42,{history_bg}); border-radius: 8px; }}"
            f"QLabel#audioHistoryOriginal {{ color: rgba(226,232,240,{text}); }}"
            f"QLabel#audioHistoryTranslation {{ color: rgba(191,219,254,{text}); }}"
            "QProgressBar { background: rgba(255,255,255,35); border: none; border-radius: 3px; }"
            "QProgressBar::chunk { background: rgba(96,165,250,190); border-radius: 3px; }"
            "QScrollArea, QScrollArea > QWidget { background: transparent; border: none; }"
            "QScrollArea > QWidget#qt_scrollarea_viewport { background: transparent; }"
            "QScrollBar:vertical { background: rgba(255,255,255,25); width: 6px; }"
            "QScrollBar::handle:vertical { background: rgba(150,200,255,150); border-radius: 3px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

    def set_click_through(self, enabled: bool) -> None:
        flag = Qt.WindowType.WindowTransparentForInput
        changed = bool(int(self.windowFlags()) & int(flag)) != enabled
        visible = self.isVisible()
        if changed:
            geometry = QRect(self.geometry())
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
            self.setWindowFlag(flag, enabled)
            self.setGeometry(geometry)
            if visible:
                self.show()
                self.raise_()
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)

        if sys.platform != "win32":
            return
        try:
            hwnd = wintypes.HWND(int(self.winId()))
            user32 = ctypes.windll.user32
            if ctypes.sizeof(ctypes.c_void_p) == 8:
                get_style = user32.GetWindowLongPtrW
                set_style = user32.SetWindowLongPtrW
                style_type = ctypes.c_longlong
            else:
                get_style = user32.GetWindowLongW
                set_style = user32.SetWindowLongW
                style_type = ctypes.c_long
            get_style.argtypes = [wintypes.HWND, ctypes.c_int]
            get_style.restype = style_type
            set_style.argtypes = [wintypes.HWND, ctypes.c_int, style_type]
            set_style.restype = style_type
            style = int(get_style(hwnd, -20))
            if enabled:
                style |= 0x00000020 | 0x00080000 | 0x08000000
            else:
                style &= ~(0x00000020 | 0x08000000)
            set_style(hwnd, -20, style)
            user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0020)
        except (AttributeError, OSError, OverflowError, TypeError, ValueError):
            pass

    def eventFilter(self, watched, event) -> bool:
        if not self.is_window_widget(watched) or self.locked:
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = event.globalPosition().toPoint()
            self.drag_origin = self.frameGeometry().topLeft()
            return True
        if event.type() == QEvent.Type.MouseMove and self.drag_start is not None and self.drag_origin is not None:
            self.move(self.drag_origin + event.globalPosition().toPoint() - self.drag_start)
            return True
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = None
            self.drag_origin = None
            return True
        return super().eventFilter(watched, event)

    def is_window_widget(self, watched) -> bool:
        return watched is self or (
            isinstance(watched, QWidget)
            and (watched is self.card or self.card.isAncestorOf(watched))
        )

    def set_locked(self, locked: bool) -> None:
        self.locked = bool(locked)
        self.set_click_through(self.locked)
        self.title_bar.set_locked(self.locked)
        self.setWindowTitle("音频实时翻译（已锁定）" if self.locked else "音频实时翻译")
        self.lock_changed.emit(self.locked)

    def restore_geometry(self, settings: AppSettings) -> None:
        if settings.audio_window_x >= 0 and settings.audio_window_y >= 0:
            self.move(settings.audio_window_x, settings.audio_window_y)

    def save_geometry(self, settings: AppSettings) -> None:
        geometry = self.geometry()
        settings.audio_window_x = geometry.x()
        settings.audio_window_y = geometry.y()

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084 and self.locked:
                    return True, -1
            except (TypeError, ValueError):
                pass
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.stop_requested.emit()
        super().closeEvent(event)
