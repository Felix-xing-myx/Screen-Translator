"""Floating real-time audio translation result window."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QRect,
    QTimer,
    Qt,
    Signal,
)
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
from .overlay import OverlayResizeMixin


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


class AudioTranslationWindow(OverlayResizeMixin, QDialog):
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
        self._current_update_revision = 0
        self._history_scroll_revision = 0
        self._current_follow_bottom = {
            "original": False,
            "translation": False,
        }
        self._current_scroll_timers: dict[str, QTimer] = {}
        self._current_hold_timer = QTimer(self)
        self._current_hold_timer.setSingleShot(True)
        self._current_hold_timer.timeout.connect(self._release_current_hold)
        self._partial_throttle_timer = QTimer(self)
        self._partial_throttle_timer.setSingleShot(True)
        self._partial_throttle_timer.setInterval(80)
        self._partial_throttle_timer.timeout.connect(self._flush_pending_partial)
        self._current_hold_active = False
        self._pending_partial: tuple[str, str] | None = None
        self._pending_completed: list[tuple[str, str]] = []
        self._current_hold_ms = 2200
        self._show_current_original = True
        self._font_scale_multiplier = 1.0
        self._font_scale = 1.0

        self.setWindowTitle("音频实时翻译")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumSize(400, 150)
        self.resize(560, 430)
        # 卡片四周保留了阴影空间，原生窗口边缘命中测试需要覆盖这段可见边界。
        self.resize_border = 18

        self.card = QWidget(self)
        self.card.setObjectName("audioCard")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(8)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 90))
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
        self.status_widget = QWidget()
        self.status_widget.setObjectName("audioStatusRow")
        self.status_widget.setLayout(status_row)

        self.current_original = self._make_text_edit(
            "检测到声音后显示原文", "audioCurrentOriginal"
        )
        self.current_translation = self._make_text_edit(
            "翻译结果将在这里显示", "audioCurrentTranslation"
        )
        self.current_original.setMinimumHeight(28)
        self.current_translation.setMinimumHeight(36)
        self.current_original.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.current_translation.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        for edit in (self.current_original, self.current_translation):
            scrollbar = edit.verticalScrollBar()
            scrollbar.sliderPressed.connect(
                lambda edit=edit: self._cancel_current_scroll_animation(edit)
            )
            scrollbar.actionTriggered.connect(
                lambda _action, edit=edit: self._cancel_current_scroll_animation(edit)
            )

        current_panel = QFrame()
        current_panel.setObjectName("audioCurrentMask")
        current_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.current_panel = current_panel
        current_layout = QVBoxLayout(current_panel)
        current_layout.setContentsMargins(10, 7, 10, 8)
        current_layout.setSpacing(2)
        current_layout.addWidget(self.current_original, 1)
        current_layout.addWidget(self.current_translation, 1)
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
        self.history_scroll.setMinimumHeight(0)
        self.history_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored
        )

        card_layout = QVBoxLayout(self.card)
        self.card_layout = card_layout
        card_layout.setContentsMargins(8, 7, 8, 8)
        card_layout.setSpacing(5)
        card_layout.addWidget(self.title_bar)
        card_layout.addWidget(self.status_widget)
        card_layout.addWidget(self.source_label)
        card_layout.addWidget(self.level_bar)
        card_layout.addWidget(current_panel)
        card_layout.addWidget(self.history_scroll, 1)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.addWidget(self.card)

        self.background_opacity = 82
        self.text_opacity = 100
        self.history_text_opacity = 100
        self.mask_opacity = 45
        self.apply_visual_style()
        self.install_overlay_resize_filter()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "history_scroll"):
            # Preserve the current translation area at compact heights.  The
            # history area is supplemental and may disappear completely.
            self.history_scroll.setVisible(self.height() > 240)
        if hasattr(self, "status_widget"):
            # The header is useful at normal size but can be removed entirely
            # when the overlay is compressed down to the live translation.
            show_header = self.height() > 380
            self.title_bar.setVisible(show_header)
            self.status_widget.setVisible(show_header)
            self.source_label.setVisible(show_header)
            self.level_bar.setVisible(show_header)
            self.card_layout.setStretch(4, 1 if not show_header else 0)
            self.card_layout.setStretch(5, 1)
        scale = min(self.width() / 560.0, self.height() / 430.0)
        scale = max(0.6, min(1.5, scale))
        self._font_scale = scale
        if not hasattr(self, "current_original"):
            return
        self._apply_current_dimensions(scale)
        self.apply_visual_style()
        for edit in (self.current_original, self.current_translation):
            if self._current_follow_bottom[self._current_edit_key(edit)]:
                QTimer.singleShot(
                    0,
                    lambda edit=edit: self._start_current_scroll_timer(
                        edit, self._current_update_revision
                    ),
                )

    def set_show_original(self, enabled: bool) -> None:
        self._show_current_original = bool(enabled)
        self.current_original.setVisible(self._show_current_original)
        self._apply_current_dimensions(self._font_scale)

    def set_font_scale(self, percentage: int) -> None:
        self._font_scale_multiplier = max(0.5, min(4.0, int(percentage) / 100))
        self.apply_visual_style()

    def _apply_current_dimensions(self, scale: float) -> None:
        original_height = max(28, round(48 * scale))
        translation_height = max(36, round(62 * scale))
        if self.height() > 380:
            if self._show_current_original:
                self.current_original.setFixedHeight(original_height)
                self.current_translation.setFixedHeight(translation_height)
            else:
                self.current_translation.setFixedHeight(
                    original_height + translation_height + 2
                )
        else:
            for edit in (self.current_original, self.current_translation):
                edit.setMaximumHeight(16777215)
            compact_original = max(24, round(34 * scale))
            compact_translation = max(30, round(44 * scale))
            if self._show_current_original:
                self.current_original.setMinimumHeight(compact_original)
                self.current_translation.setMinimumHeight(compact_translation)
            else:
                self.current_translation.setMinimumHeight(
                    compact_original + compact_translation + 2
                )

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
        snapshot = self._capture_history_scroll()
        self._history_limit = max(1, min(10, int(value)))
        while len(self._history_cards) > self._history_limit:
            self._remove_oldest_card()
        self._sync_history_content_size()
        self._schedule_history_scroll_restore(snapshot, inserted_at_top=False)

    def set_state(self, state: str) -> None:
        self.state_label.setText(state)

    def set_source(self, source: str) -> None:
        self.source_label.setText(f"音频源：{source}")

    def set_level(self, value: int) -> None:
        self.level_bar.setValue(max(0, min(100, int(value))))

    def set_speech_state(self, active: bool) -> None:
        self.speech_label.setText(
            "语音状态：检测到声音" if active else "语音状态：静音"
        )

    def update_partial(self, original: str, translated: str) -> None:
        self._pending_partial = (original, translated)
        if not self._current_hold_active and not self._partial_throttle_timer.isActive():
            self._partial_throttle_timer.start()

    def _flush_pending_partial(self) -> None:
        if self._current_hold_active or self._pending_partial is None:
            return
        original, translated = self._pending_partial
        self._pending_partial = None
        self._update_current_text(original, translated)

    def _update_current_text(self, original: str, translated: str) -> None:
        self._current_update_revision += 1
        revision = self._current_update_revision
        self._update_current_edit(self.current_original, original, revision)
        self._update_current_edit(self.current_translation, translated, revision)

    def _update_current_edit(
        self, edit: QPlainTextEdit, text: str, revision: int
    ) -> None:
        scrollbar = edit.verticalScrollBar()
        old_value = scrollbar.value()
        old_maximum = scrollbar.maximum()
        edit_key = self._current_edit_key(edit)
        follow_bottom = (
            self._current_follow_bottom[edit_key]
            or not edit.toPlainText()
            or old_maximum <= 0
            or old_value >= old_maximum - 2
        )
        self._current_follow_bottom[edit_key] = follow_bottom
        edit.setPlainText(text)
        QTimer.singleShot(
            0,
            lambda: self._start_current_scroll(
                edit, old_value, follow_bottom, revision
            ),
        )

    def _start_current_scroll(
        self,
        edit: QPlainTextEdit,
        old_value: int,
        follow_bottom: bool,
        revision: int,
    ) -> None:
        if revision != self._current_update_revision:
            return
        if follow_bottom:
            self._current_follow_bottom[self._current_edit_key(edit)] = True
            scrollbar = edit.verticalScrollBar()
            scrollbar.setValue(min(old_value, scrollbar.maximum()))
            self._start_current_scroll_timer(edit, revision)
        else:
            self._cancel_current_scroll_animation(edit)
            edit.verticalScrollBar().setValue(
                min(old_value, edit.verticalScrollBar().maximum())
            )

    def _current_edit_key(self, edit: QPlainTextEdit) -> str:
        return "original" if edit is self.current_original else "translation"

    def _start_current_scroll_timer(
        self, edit: QPlainTextEdit, revision: int
    ) -> None:
        key = self._current_edit_key(edit)
        timer = self._current_scroll_timers.get(key)
        if timer is None:
            timer = QTimer(self)
            timer.setInterval(20)
            timer.timeout.connect(
                lambda edit=edit, key=key: self._advance_current_scroll(
                    edit, key
                )
            )
            self._current_scroll_timers[key] = timer
        timer.setProperty("scrollRevision", revision)
        timer.setProperty("idleFrames", 0)
        if not timer.isActive():
            timer.start()

    def _advance_current_scroll(self, edit: QPlainTextEdit, key: str) -> None:
        timer = self._current_scroll_timers.get(key)
        if timer is None:
            return
        if not self._current_follow_bottom[key]:
            timer.stop()
            return

        scrollbar = edit.verticalScrollBar()
        target = scrollbar.maximum()
        current = scrollbar.value()
        if current >= target:
            # Keep checking briefly while QPlainTextEdit is still laying out
            # newly wrapped lines; the target can increase after this frame.
            idle_frames = int(timer.property("idleFrames") or 0) + 1
            timer.setProperty("idleFrames", idle_frames)
            if idle_frames >= 30:
                timer.stop()
            return

        # Move by a small, fixed number of pixels per frame.  This avoids the
        # scrollbar jump caused by changing its target while the document is
        # being laid out, while still following rapidly arriving partial text.
        timer.setProperty("idleFrames", 0)
        scrollbar.setValue(min(target, current + 2))

    def _cancel_current_scroll_animation(self, edit: QPlainTextEdit) -> None:
        key = self._current_edit_key(edit)
        self._current_follow_bottom[key] = False
        timer = self._current_scroll_timers.get(key)
        if timer is not None:
            timer.stop()

    def append_result(self, original: str, translated: str) -> None:
        if not original and not translated:
            return
        self._partial_throttle_timer.stop()
        self._pending_partial = None
        self._append_history_card(original, translated)
        if self._current_hold_active:
            self._pending_partial = None
            self._pending_completed.append((original, translated))
            return
        self._update_current_text(original, translated)
        self._start_current_hold()

    def _start_current_hold(self) -> None:
        self._current_hold_active = True
        self._current_hold_timer.start(self._current_hold_ms)

    def _release_current_hold(self) -> None:
        self._current_hold_active = False
        if self._pending_completed:
            original, translated = self._pending_completed.pop(0)
            self._update_current_text(original, translated)
            self._start_current_hold()
            return
        if self._pending_partial is not None:
            original, translated = self._pending_partial
            self._pending_partial = None
            self._update_current_text(original, translated)

    def _append_history_card(self, original: str, translated: str) -> None:
        history_snapshot = self._capture_history_scroll()
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
        original_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        translation_label = QLabel(translated or "（无译文）")
        translation_label.setObjectName("audioHistoryTranslation")
        translation_label.setWordWrap(True)
        translation_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        card_layout.addWidget(translation_label)
        card_layout.addWidget(original_label)
        self.history_layout.insertWidget(0, card)
        self._history_cards.insert(0, card)
        self._sync_history_content_size()
        self._schedule_history_scroll_restore(
            history_snapshot, inserted_at_top=True
        )

    def _remove_oldest_card(self) -> None:
        if not self._history_cards:
            return
        card = self._history_cards.pop()
        self.history_layout.removeWidget(card)
        card.deleteLater()
        self._sync_history_content_size()

    def _sync_history_content_size(self) -> None:
        self.history_layout.activate()
        self.history_content.setMinimumHeight(
            max(0, self.history_layout.sizeHint().height())
        )

    def _capture_history_scroll(self) -> tuple[int, int, int]:
        scrollbar = self.history_scroll.verticalScrollBar()
        return (
            scrollbar.value(),
            scrollbar.maximum(),
            self.history_content.sizeHint().height(),
        )

    def _schedule_history_scroll_restore(
        self,
        snapshot: tuple[int, int, int],
        inserted_at_top: bool,
    ) -> None:
        self._history_scroll_revision += 1
        revision = self._history_scroll_revision

        def restore() -> None:
            if revision != self._history_scroll_revision:
                return
            scrollbar = self.history_scroll.verticalScrollBar()
            old_value, old_maximum, old_height = snapshot
            if old_maximum <= 0 or old_value <= 2:
                target = 0
            elif old_value >= old_maximum - 2:
                target = scrollbar.maximum()
            elif inserted_at_top:
                delta = max(
                    0, self.history_content.sizeHint().height() - old_height
                )
                target = old_value + delta
            else:
                target = old_value
            scrollbar.setValue(min(max(target, 0), scrollbar.maximum()))

        QTimer.singleShot(0, restore)

    def clear(self) -> None:
        self._current_hold_timer.stop()
        self._partial_throttle_timer.stop()
        self._current_hold_active = False
        self._pending_partial = None
        self._pending_completed.clear()
        self._current_update_revision += 1
        self._history_scroll_revision += 1
        self._current_follow_bottom["original"] = False
        self._current_follow_bottom["translation"] = False
        for timer in self._current_scroll_timers.values():
            timer.stop()
        self.current_original.clear()
        self.current_translation.clear()
        while self._history_cards:
            self._remove_oldest_card()
        self._sync_history_content_size()
        self.history_scroll.verticalScrollBar().setValue(0)
        self.set_level(0)
        self.set_speech_state(False)
    def set_background_opacity(self, percentage: int) -> None:
        self.background_opacity = max(0, min(100, int(percentage)))
        self.apply_visual_style()

    def set_text_opacity(self, percentage: int) -> None:
        self.text_opacity = max(30, min(100, int(percentage)))
        self.apply_visual_style()

    def set_history_text_opacity(self, percentage: int) -> None:
        self.history_text_opacity = max(30, min(100, int(percentage)))
        self.apply_visual_style()

    def set_mask_opacity(self, percentage: int) -> None:
        self.mask_opacity = max(0, min(100, int(percentage)))
        self.apply_visual_style()

    def apply_visual_style(self) -> None:
        bg = round(255 * self.background_opacity / 100)
        history_bg = round(165 * self.background_opacity / 100)
        text = round(255 * self.text_opacity / 100)
        history_text = round(255 * self.history_text_opacity / 100)
        mask = round(255 * self.mask_opacity / 100)
        chrome = round(255 * self.background_opacity / 100)
        border = round(150 * self.background_opacity / 100)
        text_scale = self._font_scale * self._font_scale_multiplier
        title_size = max(9, round(12 * self._font_scale))
        lock_size = max(8, round(10 * self._font_scale))
        chrome_size = max(9, round(13 * self._font_scale))
        original_size = max(10, round(13 * text_scale))
        translation_size = max(12, round(16 * text_scale))
        history_size = max(9, round(12 * text_scale))
        progress_bg = round(35 * self.background_opacity / 100)
        progress_chunk = round(190 * self.background_opacity / 100)
        scrollbar_bg = round(25 * self.background_opacity / 100)
        scrollbar_handle = round(150 * self.background_opacity / 100)
        self.setWindowOpacity(1.0)
        self.card_shadow.setColor(QColor(0, 0, 0, round(150 * self.background_opacity / 100)))
        self.setStyleSheet(
            f"QWidget#audioCard {{ background: rgba(10,17,22,{bg}); "
            f"border: 1px solid rgba(107,216,255,{border}); border-radius: 8px; }}"
            "QWidget#audioTitleBar { background: transparent; "
            "border-bottom: 1px solid rgba(93,112,122,120); }"
            f"QLabel#audioTitle {{ color: rgba(231,238,241,{chrome}); font-size: {title_size}px; font-weight: 600; }}"
            f"QLabel#audioLockState {{ color: rgba(195,241,255,{chrome}); font-size: {lock_size}px; font-weight: 600; }}"
            f"QLabel#audioState, QLabel#audioSource, QLabel#audioSpeech {{ color: rgba(231,238,241,{chrome}); font-size: {chrome_size}px; }}"
            f"QFrame#audioCurrentMask {{ background: rgba(17,27,33,{mask}); border: 1px solid rgba(44,60,69,130); border-radius: 6px; }}"
            f"QPlainTextEdit#audioCurrentOriginal {{ color: rgba(231,238,241,{text}); font-size: {original_size}px; background: transparent; border: none; padding: 1px; }}"
            f"QPlainTextEdit#audioCurrentTranslation {{ color: rgba(231,238,241,{text}); font-size: {translation_size}px; font-weight: 600; background: transparent; border: none; padding: 1px; }}"
            f"QFrame#audioHistoryCard {{ background: rgba(13,20,25,{history_bg}); border: 1px solid rgba(44,60,69,130); border-radius: 6px; }}"
            f"QLabel#audioHistoryOriginal {{ color: rgba(225,234,237,{history_text}); font-size: {history_size}px; }}"
            f"QLabel#audioHistoryTranslation {{ color: rgba(195,241,255,{history_text}); font-size: {history_size}px; }}"
            f"QProgressBar {{ background: rgba(93,112,122,{progress_bg}); border: none; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background: rgba(107,216,255,{progress_chunk}); border-radius: 2px; }}"
            "QScrollArea, QScrollArea > QWidget { background: transparent; border: none; }"
            "QScrollArea > QWidget#qt_scrollarea_viewport { background: transparent; }"
            f"QScrollBar:vertical {{ background: transparent; border: none; width: 7px; }}"
            f"QScrollBar::handle:vertical {{ background: rgba(93,112,122,{scrollbar_handle}); border-radius: 3px; min-height: 24px; }}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
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
        self.resize(
            max(self.minimumWidth(), settings.audio_window_width),
            max(self.minimumHeight(), settings.audio_window_height),
        )

    def save_geometry(self, settings: AppSettings) -> None:
        geometry = self.geometry()
        settings.audio_window_x = geometry.x()
        settings.audio_window_y = geometry.y()
        settings.audio_window_width = geometry.width()
        settings.audio_window_height = geometry.height()

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
        self.remove_overlay_resize_filter()
        self.stop_requested.emit()
        super().closeEvent(event)
