"""Floating translation result window."""

from __future__ import annotations

import ctypes
import math
import sys
from ctypes import wintypes

from PySide6.QtCore import QEvent, QPoint, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..text_utils import compact_display_text
from .overlay import OverlayResizeMixin


class WindowTitleBar(QWidget):
    def __init__(self, window, title: str):
        super().__init__(window)
        self.window = window
        self.setObjectName("resultTitleBar")
        self.setFixedHeight(28)
        self.setMouseTracking(True)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("resultTitle")
        self.lock_label = QLabel("")
        self.lock_label.setObjectName("resultLockState")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.addWidget(self.title_label)
        layout.addStretch(1)
        layout.addWidget(self.lock_label)

    def set_locked(self, locked: bool) -> None:
        self.lock_label.setText("LOCKED" if locked else "")


class WrappedTranslationLabel(QLabel):
    """A plain-text label whose height remains correct as the window resizes."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        if width <= 0:
            return super().heightForWidth(width)
        document = QTextDocument()
        document.setDefaultFont(self.font())
        document.setPlainText(self.text())
        text_width = max(
            1,
            width
            - self.contentsMargins().left()
            - self.contentsMargins().right(),
        )
        document.setTextWidth(text_width)
        return (
            math.ceil(document.size().height())
            + self.contentsMargins().top()
            + self.contentsMargins().bottom()
            + 2
        )


class MonitorResultWindow(OverlayResizeMixin, QDialog):
    stop_requested = Signal()
    lock_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.locked = False
        self.drag_origin: QPoint | None = None
        self.drag_start: QPoint | None = None
        self.setWindowTitle("持续翻译")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumSize(360, 150)
        self.resize(520, 220)

        self.card = QWidget(self)
        self.card.setObjectName("resultCard")
        self.card.setMouseTracking(True)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(8)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.card.setGraphicsEffect(shadow)
        self.card_shadow = shadow

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(8, 7, 8, 8)
        self.title_bar = WindowTitleBar(self, "Screen Translator")
        card_layout.addWidget(self.title_bar)

        self.translation_cards: list[tuple[QFrame, QLabel]] = []
        self.translation_content = QWidget()
        self.translation_content.setObjectName("translationContent")
        self.translation_content.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self.translation_content.setAutoFillBackground(False)
        self.translation_content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        content_layout = QVBoxLayout(self.translation_content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(6)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.translation_cards_layout = content_layout

        self.translation_scroll = QScrollArea()
        self.translation_scroll.setWidgetResizable(True)
        self.translation_scroll.setMinimumSize(0, 0)
        self.translation_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.translation_scroll.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self.translation_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.translation_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.translation_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.translation_scroll.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.translation_scroll.setContentsMargins(0, 0, 0, 0)
        self.translation_scroll.viewport().setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self.translation_scroll.viewport().setAutoFillBackground(False)
        self.translation_scroll.viewport().setStyleSheet(
            "background: transparent; border: none;"
        )
        self.translation_scroll.setWidget(self.translation_content)
        card_layout.addWidget(self.translation_scroll, 1)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(7, 7, 7, 7)
        root_layout.addWidget(self.card)
        self.background_opacity = 82
        self.text_opacity = 100
        self.translation_font_size = 14
        self.mask_opacity = 45
        self.apply_visual_style()
        self.scroll_timer = QTimer(self)
        self.scroll_timer.setInterval(45)
        self.scroll_timer.timeout.connect(self.auto_scroll_step)
        self.scroll_pause_timer = QTimer(self)
        self.scroll_pause_timer.setSingleShot(True)
        self.scroll_pause_timer.timeout.connect(self.start_auto_scroll)
        self.manual_scroll_pause_timer = QTimer(self)
        self.manual_scroll_pause_timer.setSingleShot(True)
        self.manual_scroll_pause_timer.timeout.connect(self._resume_after_manual_scroll)
        self.scroll_speed = 1
        self._manual_scroll_paused = False
        self.scroll_direction = 1
        self.display_revision = 0
        self.pending_scroll_state: tuple[int, bool, int] | None = None
        scrollbar = self.translation_scroll.verticalScrollBar()
        scrollbar.sliderPressed.connect(self._pause_auto_scroll_for_user)
        scrollbar.sliderMoved.connect(
            lambda _value: self._pause_auto_scroll_for_user()
        )
        scrollbar.actionTriggered.connect(
            lambda _action: self._pause_auto_scroll_for_user()
        )
        for widget in (
            self.translation_scroll,
            self.translation_scroll.viewport(),
            self.translation_content,
        ):
            widget.installEventFilter(self)
        self.install_overlay_resize_filter()

    def update_result(self, original: str, translated: str) -> None:
        cleaned = compact_display_text(translated, preserve_lines=True)
        self.set_display_entries([(None, cleaned)] if cleaned else [])

    def update_regions(self, regions: list[tuple[int, str]]) -> None:
        """在同一个滚动内容中显示所有区域的紧凑译文。"""
        entries = []
        for region_id, translated in regions:
            cleaned = compact_display_text(translated, preserve_lines=True)
            if cleaned:
                entries.append((region_id, cleaned))
        self.set_display_entries(entries)

    def set_display_entries(self, entries: list[tuple[int | None, str]]) -> None:
        # 内容刷新期间滚动条范围会短暂归零。连续收到多个区域的结果时，
        # 沿用第一次刷新前保存的位置，避免后面的区域永远被顶端内容挡住。
        if self.pending_scroll_state is None:
            scrollbar = self.translation_scroll.verticalScrollBar()
            old_maximum = scrollbar.maximum()
            self.pending_scroll_state = (
                scrollbar.value(),
                old_maximum > 0 and scrollbar.value() >= old_maximum - 2,
                self.scroll_direction,
            )
        self.display_revision += 1
        revision = self.display_revision
        self.clear_result(restart_scroll=False)
        for region_id, text in entries:
            card = QFrame(self.translation_content)
            card.setObjectName("translationCard")
            card.setFrameShape(QFrame.Shape.NoFrame)
            card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            card_layout.setSpacing(2)

            if region_id is not None:
                header = QLabel(f"区域 {region_id + 1}", card)
                header.setObjectName("resultRegionHeader")
                card_layout.addWidget(header)

            body = WrappedTranslationLabel(text, card)
            body.setObjectName("resultTranslation")
            body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            body.setAutoFillBackground(False)
            card_layout.addWidget(body)
            self.translation_cards_layout.addWidget(card)
            self.translation_cards.append((card, body))

        self.show()
        self.raise_()
        self.translation_cards_layout.activate()
        self._update_translation_body_heights()
        self.translation_content.updateGeometry()
        QTimer.singleShot(0, lambda rev=revision: self.fit_translation_font(rev))

    def clear_result(self, restart_scroll: bool = True) -> None:
        for card, _body in self.translation_cards:
            self.translation_cards_layout.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self.translation_cards.clear()
        self.scroll_timer.stop()
        self.scroll_pause_timer.stop()
        if restart_scroll:
            self.display_revision += 1
            self.pending_scroll_state = None
            self.restart_auto_scroll()

    def fit_translation_font(self, revision: int | None = None) -> None:
        if revision is None:
            scrollbar = self.translation_scroll.verticalScrollBar()
            maximum = scrollbar.maximum()
            self.pending_scroll_state = (
                scrollbar.value(),
                maximum > 0 and scrollbar.value() >= maximum - 2,
                self.scroll_direction,
            )
            self.display_revision += 1
            revision = self.display_revision
        elif revision != self.display_revision:
            return
        if not self.translation_cards:
            self.restore_scroll_after_update(revision)
            return
        selected_font = QFont(self.font())
        # A font created from a stylesheet can report an unresolved size as
        # -1 during Qt startup. Never pass that value to setPointSize(), which
        # otherwise emits a QFont warning when settings dialogs are opened.
        point_size = int(self.translation_font_size)
        if point_size <= 0:
            point_size = 14
        selected_font.setPointSize(point_size)
        for _card, body in self.translation_cards:
            body.setFont(selected_font)
            body.updateGeometry()
        self.translation_cards_layout.activate()
        self._update_translation_body_heights()
        self.translation_content.adjustSize()
        self.translation_content.updateGeometry()
        self.translation_scroll.updateGeometry()
        QTimer.singleShot(0, lambda rev=revision: self.restore_scroll_after_update(rev))

    def _update_translation_body_heights(self) -> None:
        """Give wrapped labels their real height at the current viewport width.

        QScrollArea may ask its child for a size hint before the child has
        received its final width.  Without this second pass, the content
        widget can become taller than its card, leaving a blank scrollable
        tail or clipping the label inside the card.
        """
        for _card, body in self.translation_cards:
            if body.width() <= 0:
                continue
            body.setMinimumHeight(max(1, body.heightForWidth(body.width())))
            body.updateGeometry()
        self.translation_cards_layout.activate()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._refresh_translation_layout_after_resize)

    def _refresh_translation_layout_after_resize(self) -> None:
        if not self.translation_cards:
            return
        self.translation_cards_layout.activate()
        self._update_translation_body_heights()
        self.translation_content.adjustSize()
        self.translation_content.updateGeometry()
        self.translation_scroll.updateGeometry()

    def restore_scroll_after_update(self, revision: int) -> None:
        if revision != self.display_revision:
            return
        state = self.pending_scroll_state
        self.pending_scroll_state = None
        if state is None:
            state = (0, False, 1)
        old_value, followed_bottom, old_direction = state
        scrollbar = self.translation_scroll.verticalScrollBar()
        maximum = scrollbar.maximum()
        scrollbar.setValue(maximum if followed_bottom else min(old_value, maximum))
        self.scroll_direction = old_direction
        if maximum > 0 and self.isVisible() and not self._manual_scroll_paused:
            self.scroll_pause_timer.start(1200)

    def restart_auto_scroll(self) -> None:
        self.scroll_timer.stop()
        self.scroll_pause_timer.stop()
        self.manual_scroll_pause_timer.stop()
        self._manual_scroll_paused = False
        scrollbar = self.translation_scroll.verticalScrollBar()
        scrollbar.setValue(0)
        self.scroll_direction = 1
        if scrollbar.maximum() > 0 and self.isVisible():
            self.scroll_pause_timer.start(1200)

    def start_auto_scroll(self) -> None:
        scrollbar = self.translation_scroll.verticalScrollBar()
        if (
            scrollbar.maximum() > 0
            and self.isVisible()
            and not self._manual_scroll_paused
        ):
            self.scroll_timer.start()

    def _pause_auto_scroll_for_user(self) -> None:
        """Keep user-selected content visible for four seconds."""
        scrollbar = self.translation_scroll.verticalScrollBar()
        if scrollbar.maximum() <= 0 or not self.isVisible():
            return
        self.scroll_timer.stop()
        self.scroll_pause_timer.stop()
        self._manual_scroll_paused = True
        self.manual_scroll_pause_timer.start(4000)

    def _resume_after_manual_scroll(self) -> None:
        self._manual_scroll_paused = False
        self.start_auto_scroll()

    def auto_scroll_step(self) -> None:
        scrollbar = self.translation_scroll.verticalScrollBar()
        maximum = scrollbar.maximum()
        if maximum <= 0 or not self.isVisible():
            self.scroll_timer.stop()
            return
        next_value = scrollbar.value() + self.scroll_direction * self.scroll_speed
        if next_value >= maximum:
            scrollbar.setValue(maximum)
            self.scroll_direction = -1
            self.scroll_timer.stop()
            self.scroll_pause_timer.start(1500)
        elif next_value <= 0:
            scrollbar.setValue(0)
            self.scroll_direction = 1
            self.scroll_timer.stop()
            self.scroll_pause_timer.start(1200)
        else:
            scrollbar.setValue(next_value)

    def resume_auto_scroll_after_window_change(self) -> None:
        """窗口锁定状态切换后，从当前位置恢复自动滚动。"""
        self.scroll_timer.stop()
        self.scroll_pause_timer.stop()
        self.manual_scroll_pause_timer.stop()
        self._manual_scroll_paused = False
        scrollbar = self.translation_scroll.verticalScrollBar()
        if scrollbar.maximum() > 0 and self.isVisible():
            self.scroll_pause_timer.start(300)

    def set_window_opacity(self, percentage: int) -> None:
        # 兼容旧代码：此参数现在只控制背景，不再降低翻译文字的清晰度。
        self.set_background_opacity(percentage)

    def set_background_opacity(self, percentage: int) -> None:
        self.background_opacity = max(0, min(100, int(percentage)))
        self.apply_visual_style()

    def set_text_opacity(self, percentage: int) -> None:
        self.text_opacity = max(30, min(100, int(percentage)))
        self.apply_visual_style()

    def set_mask_opacity(self, percentage: int) -> None:
        self.mask_opacity = max(0, min(100, int(percentage)))
        self.apply_visual_style()

    def set_translation_font_size(self, point_size: int) -> None:
        self.translation_font_size = max(9, min(28, int(point_size)))
        self.fit_translation_font()

    def set_scroll_speed(self, speed: int) -> None:
        self.scroll_speed = max(1, min(10, int(speed)))

    def apply_visual_style(self) -> None:
        background_alpha = round(255 * self.background_opacity / 100)
        text_alpha = round(255 * self.text_opacity / 100)
        mask_alpha = round(255 * self.mask_opacity / 100)
        chrome_alpha = round(255 * self.background_opacity / 100)
        border_alpha = round(150 * self.background_opacity / 100)
        self.setWindowOpacity(1.0)
        self.card_shadow.setColor(QColor(0, 0, 0, round(150 * self.background_opacity / 100)))
        self.translation_content.setStyleSheet("background: transparent;")
        self.setStyleSheet(
            f"QWidget#resultCard {{ background: rgba(10, 17, 22, {background_alpha}); "
            f"border: 1px solid rgba(107, 216, 255, {border_alpha}); border-radius: 8px; }}"
            "QWidget#resultTitleBar { background: transparent; "
            "border-bottom: 1px solid rgba(93, 112, 122, 120); }"
            f"QLabel#resultTitle {{ color: rgba(231, 238, 241, {chrome_alpha}); font-size: 12px; font-weight: 600; }}"
            f"QLabel#resultLockState {{ color: rgba(195, 241, 255, {chrome_alpha}); font-size: 10px; font-weight: 600; }}"
            f"QFrame#translationCard {{ background: rgba(17, 27, 33, {mask_alpha}); border: 1px solid rgba(44, 60, 69, 130); border-radius: 6px; }}"
            f"QLabel#resultRegionHeader {{ color: rgba(107, 216, 255, {text_alpha}); font-size: 10px; font-weight: 600; }}"
            f"QLabel#resultTranslation {{ color: rgba(231, 238, 241, {text_alpha}); padding: 1px; }}"
            "QScrollArea, QScrollArea > QWidget { background: transparent; border: none; }"
            "QScrollArea > QWidget#qt_scrollarea_viewport { background: transparent; }"
            "QScrollBar:vertical { background: transparent; width: 7px; }"
            "QScrollBar::handle:vertical { background: rgba(93,112,122,180); "
            "border-radius: 3px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

    def set_click_through(self, enabled: bool) -> None:
        """让锁定后的分层窗口把鼠标交给下方任意程序。"""
        transparent_input_flag = Qt.WindowType.WindowTransparentForInput
        has_transparent_input = bool(int(self.windowFlags()) & int(transparent_input_flag))
        window_flags_changed = has_transparent_input != enabled
        was_visible = self.isVisible()
        if window_flags_changed:
            saved_geometry = QRect(self.geometry())
            # 先同步 Qt 的鼠标透明属性，再切换窗口标志，避免解锁时
            # 旧的 WA_TransparentForMouseEvents 把透明输入标志重新带回去。
            self.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                enabled,
            )
            self.setWindowFlag(transparent_input_flag, enabled)
            self.setGeometry(saved_geometry)
            if was_visible:
                self.show()
                self.raise_()
        else:
            self.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                enabled,
            )
        if window_flags_changed and was_visible:
            QTimer.singleShot(0, self.resume_auto_scroll_after_window_change)
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

            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000
            WS_EX_NOACTIVATE = 0x08000000
            style = int(get_style(hwnd, GWL_EXSTYLE))
            if enabled:
                style |= WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE
            else:
                style &= ~(WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
            set_style(hwnd, GWL_EXSTYLE, style)

            # 通知 Windows 立即重新计算命中测试；不改变大小和位置。
            user32.SetWindowPos(
                hwnd,
                wintypes.HWND(-1),  # HWND_TOPMOST
                0,
                0,
                0,
                0,
                0x0001 | 0x0002 | 0x0010 | 0x0020,  # NOSIZE|NOMOVE|NOACTIVATE|FRAMECHANGED
            )
        except (AttributeError, OSError, OverflowError, TypeError, ValueError):
            # 非 Windows 环境或窗口句柄尚未准备好时，仍保留 Qt 层的行为。
            pass

    def eventFilter(self, watched, event) -> bool:
        if watched in (
            self.translation_scroll,
            self.translation_scroll.viewport(),
            self.translation_content,
        ):
            if event.type() == QEvent.Type.Wheel:
                self._pause_auto_scroll_for_user()
            elif event.type() == QEvent.Type.KeyPress and event.key() in (
                Qt.Key.Key_Up,
                Qt.Key.Key_Down,
                Qt.Key.Key_PageUp,
                Qt.Key.Key_PageDown,
                Qt.Key.Key_Home,
                Qt.Key.Key_End,
            ):
                self._pause_auto_scroll_for_user()
        return super().eventFilter(watched, event)

    def is_result_widget(self, watched) -> bool:
        if watched is self:
            return True
        if not isinstance(watched, QWidget):
            return False
        return watched is self.card or self.card.isAncestorOf(watched)

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        self.set_click_through(locked)
        self.title_bar.set_locked(locked)
        if locked:
            self.setWindowTitle("持续翻译（已锁定）")
        else:
            self.setWindowTitle("持续翻译")
        self.lock_changed.emit(locked)

    def restore_geometry(self, settings: AppSettings, screen_geometry: QRect) -> None:
        width = max(self.minimumWidth(), settings.overlay_width)
        height = max(self.minimumHeight(), settings.overlay_height)
        self.resize(width, height)
        if settings.overlay_x < 0 or settings.overlay_y < 0:
            self.move(
                screen_geometry.right() - width - 20,
                screen_geometry.top() + 20,
            )
            return
        x = max(screen_geometry.left(), min(settings.overlay_x, screen_geometry.right() - width + 1))
        y = max(screen_geometry.top(), min(settings.overlay_y, screen_geometry.bottom() - height + 1))
        self.move(x, y)

    def save_geometry(self, settings: AppSettings) -> None:
        geometry = self.geometry()
        settings.overlay_x = geometry.x()
        settings.overlay_y = geometry.y()
        settings.overlay_width = geometry.width()
        settings.overlay_height = geometry.height()

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084:  # WM_NCHITTEST
                    # Keep the window in the client hit-test path.  Dragging
                    # is handled by OverlayResizeMixin so it can coexist
                    # with the same event stream used for edge resizing.
                    pass
            except (TypeError, ValueError):
                pass
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event) -> None:
        self.remove_overlay_resize_filter()
        self.scroll_timer.stop()
        self.scroll_pause_timer.stop()
        self.manual_scroll_pause_timer.stop()
        self.stop_requested.emit()
        super().closeEvent(event)

    def hideEvent(self, event) -> None:
        self.scroll_timer.stop()
        self.scroll_pause_timer.stop()
        self.manual_scroll_pause_timer.stop()
        super().hideEvent(event)
