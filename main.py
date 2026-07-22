from __future__ import annotations

import json
import html
import os
import re
import sys
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, asdict
from pathlib import Path

from mss import MSS
import requests
from PIL import Image, ImageOps
from PySide6.QtCore import (
    QAbstractNativeEventFilter,
    QEvent,
    QPoint,
    QRect,
    QTimer,
    QThread,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)
import pytesseract


APP_NAME = "ScreenTranslator"

MAIN_STYLE_SHEET = """
QMainWindow, QWidget#mainRoot {
    background: #0b1020;
    color: #e5e7eb;
}
QGroupBox {
    background: #111827;
    border: 1px solid #26344d;
    border-radius: 12px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 600;
    color: #bfdbfe;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QPlainTextEdit {
    background: #0f172a;
    border: 1px solid #24324a;
    border-radius: 8px;
    color: #f8fafc;
    selection-background-color: #2563eb;
    padding: 8px;
}
QPushButton {
    background: #2563eb;
    border: 1px solid #3b82f6;
    border-radius: 8px;
    color: white;
    padding: 9px 14px;
    font-weight: 600;
}
QPushButton:hover { background: #3b82f6; }
QPushButton:pressed { background: #1d4ed8; }
QPushButton:disabled { background: #26344d; color: #94a3b8; border-color: #26344d; }
QSlider::groove:horizontal { height: 5px; background: #26344d; border-radius: 2px; }
QSlider::handle:horizontal { width: 16px; margin: -6px 0; background: #60a5fa; border-radius: 8px; }
QLabel#statusLabel { color: #93c5fd; padding: 4px 0; }
QLabel#opacityLabel { color: #cbd5e1; }
"""


@dataclass
class AppSettings:
    translation_url: str = "https://api.mymemory.translated.net/get"
    translation_api_key: str = ""
    tesseract_path: str = ""
    source_language: str = "en"
    target_language: str = "zh-CN"
    hotkey: str = "Ctrl+Shift+T"
    overlay_x: int = -1
    overlay_y: int = -1
    overlay_opacity: int = 82
    overlay_text_opacity: int = 100
    overlay_font_size: int = 14
    overlay_mask_opacity: int = 45


@dataclass
class MonitorRegion:
    rect: QRect
    enabled: bool = True
    last_text: str = ""
    translated: str = ""


def settings_path() -> Path:
    app_data = os.environ.get("APPDATA") or str(Path.home())
    folder = Path(app_data) / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "settings.json"


def load_settings() -> AppSettings:
    path = settings_path()
    if not path.exists():
        return AppSettings()
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        settings = AppSettings(**{key: values[key] for key in asdict(AppSettings()) if key in values})
        if settings.translation_url == "https://libretranslate.com/translate":
            settings.translation_url = AppSettings().translation_url
            settings.target_language = AppSettings().target_language
        return settings
    except (OSError, ValueError, TypeError):
        return AppSettings()


def save_settings(settings: AppSettings) -> None:
    settings_path().write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def recognize_english(image: Image.Image, tesseract_path: str = "") -> str:
    """识别屏幕截图中的英文，集中处理路径、预处理和备用版面模式。"""
    configured_path = tesseract_path.strip()
    if configured_path:
        candidate = Path(configured_path)
        if candidate.is_dir():
            candidate = candidate / "tesseract.exe"
        if not candidate.is_file():
            raise RuntimeError(
                f"找不到 Tesseract 可执行文件：{candidate}\n"
                "请在设置中选择 E:\\Tesseract OCR\\tesseract.exe。"
            )
        pytesseract.pytesseract.tesseract_cmd = str(candidate)

    # 游戏字幕和网页小字通常只有十几像素高。先放大、转灰度并增强
    # 对比度，可以显著降低“截图有字但 OCR 返回空”的情况。
    ocr_image = ImageOps.grayscale(image.convert("RGB"))
    ocr_image = ImageOps.autocontrast(ocr_image)
    if max(ocr_image.size) < 3200:
        ocr_image = ocr_image.resize(
            (ocr_image.width * 2, ocr_image.height * 2),
            Image.Resampling.LANCZOS,
        )

    # psm 11 适合屏幕上分散的字幕、按钮和多行文本；如果当前画面
    # 更像一个完整段落，再用 psm 6 做一次备用识别。
    text = pytesseract.image_to_string(
        ocr_image, lang="eng", config="--oem 3 --psm 11"
    ).strip()
    if not text:
        text = pytesseract.image_to_string(
            ocr_image, lang="eng", config="--oem 3 --psm 6"
        ).strip()
    return text


def compact_display_text(text: str) -> str:
    """压缩译文中的多余换行、制表符和连续空格，提升阅读密度。"""
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()


def hotkey_to_win32(hotkey: str) -> tuple[int, int]:
    sequence = QKeySequence.fromString(hotkey, QKeySequence.SequenceFormat.PortableText)
    if sequence.isEmpty() or sequence.count() != 1:
        raise ValueError("热键必须是一个组合键，例如 Ctrl+Shift+T。")

    combination = sequence[0]
    qt_key = combination.key()
    qt_modifiers = combination.keyboardModifiers()
    modifiers = 0
    if qt_modifiers & Qt.KeyboardModifier.ControlModifier:
        modifiers |= 0x0002
    if qt_modifiers & Qt.KeyboardModifier.AltModifier:
        modifiers |= 0x0001
    if qt_modifiers & Qt.KeyboardModifier.ShiftModifier:
        modifiers |= 0x0004
    if qt_modifiers & Qt.KeyboardModifier.MetaModifier:
        modifiers |= 0x0008
    if modifiers == 0:
        raise ValueError("全局热键至少需要 Ctrl、Alt、Shift 或 Windows 键中的一个。")

    if Qt.Key.Key_A <= qt_key <= Qt.Key.Key_Z:
        virtual_key = qt_key
    elif Qt.Key.Key_0 <= qt_key <= Qt.Key.Key_9:
        virtual_key = qt_key
    elif Qt.Key.Key_F1 <= qt_key <= Qt.Key.Key_F24:
        virtual_key = 0x70 + (qt_key - Qt.Key.Key_F1)
    else:
        virtual_key = {
            Qt.Key.Key_Escape: 0x1B,
            Qt.Key.Key_Tab: 0x09,
            Qt.Key.Key_Backspace: 0x08,
            Qt.Key.Key_Return: 0x0D,
            Qt.Key.Key_Enter: 0x0D,
            Qt.Key.Key_Space: 0x20,
            Qt.Key.Key_Insert: 0x2D,
            Qt.Key.Key_Delete: 0x2E,
            Qt.Key.Key_Home: 0x24,
            Qt.Key.Key_End: 0x23,
            Qt.Key.Key_PageUp: 0x21,
            Qt.Key.Key_PageDown: 0x22,
            Qt.Key.Key_Left: 0x25,
            Qt.Key.Key_Up: 0x26,
            Qt.Key.Key_Right: 0x27,
            Qt.Key.Key_Down: 0x28,
            Qt.Key.Key_Plus: 0xBB,
            Qt.Key.Key_Minus: 0xBD,
        }.get(qt_key)
    if virtual_key is None:
        raise ValueError("暂不支持这个按键，请使用字母、数字、F1-F24 或常见功能键。")
    return modifiers, int(virtual_key)


class HotkeyEdit(QLineEdit):
    """A small, explicit hotkey recorder that works reliably on Windows."""

    _modifier_keys = {
        Qt.Key.Key_Control,
        Qt.Key.Key_Shift,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Meta,
    }

    def __init__(self, hotkey: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(hotkey)
        self.setPlaceholderText("点击后按下组合键，例如 Ctrl+Alt+T")
        self.setToolTip("点击输入框后直接按下新的组合键；按 Backspace 可清空")

    def keyPressEvent(self, event) -> None:
        key = event.key()
        modifiers = event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.ShiftModifier
            | Qt.KeyboardModifier.MetaModifier
        )
        if key in self._modifier_keys:
            self.setPlaceholderText("请继续按一个主键，例如 T、F2 或方向键")
            event.accept()
            return
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and not modifiers:
            self.clear()
            self.setPlaceholderText("点击后按下组合键，例如 Ctrl+Alt+T")
            event.accept()
            return
        if not modifiers:
            self.setPlaceholderText("全局热键至少需要 Ctrl、Alt、Shift 或 Windows 键")
            event.accept()
            return

        value = modifiers.value | int(key)
        hotkey = QKeySequence(value).toString(QKeySequence.SequenceFormat.PortableText)
        if hotkey:
            self.setText(hotkey)
            self.setPlaceholderText("点击后按下组合键，例如 Ctrl+Alt+T")
        event.accept()


class GlobalHotkeyFilter(QAbstractNativeEventFilter):
    """Register a user-selected Windows global hotkey and forward WM_HOTKEY to Qt."""

    WM_HOTKEY = 0x0312
    HOTKEY_ID = 0x53435254
    MOD_NOREPEAT = 0x4000

    def __init__(self, hwnd: int, hotkey: str, callback):
        super().__init__()
        self._hwnd = int(hwnd)
        self._callback = callback
        self._hotkey = hotkey
        modifiers, virtual_key = hotkey_to_win32(hotkey)
        self._user32 = ctypes.windll.user32
        self._registered = bool(
            self._user32.RegisterHotKey(
                self._hwnd,
                self.HOTKEY_ID,
                modifiers | self.MOD_NOREPEAT,
                virtual_key,
            )
        )
        if not self._registered:
            raise RuntimeError(f"无法注册全局热键 {hotkey}，可能已被其他程序占用。")

    def nativeEventFilter(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return False, 0
        try:
            msg = wintypes.MSG.from_address(int(message))
        except (TypeError, ValueError):
            return False, 0
        if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
            self._callback()
            return True, 0
        return False, 0

    def unregister(self) -> None:
        if self._registered:
            self._user32.UnregisterHotKey(self._hwnd, self.HOTKEY_ID)
            self._registered = False


class CaptureOverlay(QDialog):
    selected = Signal(QRect)

    def __init__(
        self,
        screen_geometry: QRect,
        parent: QWidget | None = None,
        instruction: str = "拖动鼠标框选英文区域，按 Esc 取消",
    ):
        super().__init__(parent)
        self.setWindowTitle("选择翻译区域")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setGeometry(screen_geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.instruction = instruction
        self.start_point: QPoint | None = None
        self.end_point: QPoint | None = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.grabKeyboard()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.reject()
            return True
        return super().event(event)

    def closeEvent(self, event) -> None:
        self.releaseKeyboard()
        super().closeEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))
        if self.start_point is None or self.end_point is None:
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(20, 35, self.instruction)
            return
        selection = QRect(self.start_point, self.end_point).normalized()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.fillRect(selection, Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(QPen(QColor(0, 190, 255), 2))
        painter.drawRect(selection)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.position().toPoint()
            self.end_point = self.start_point
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.start_point is not None:
            self.end_point = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self.start_point is None:
            return
        self.end_point = event.position().toPoint()
        selection = QRect(self.start_point, self.end_point).normalized()
        if selection.width() >= 8 and selection.height() >= 8:
            self.selected.emit(selection)
            self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.reject()
        else:
            super().keyPressEvent(event)


class MultiRegionOverlay(QDialog):
    """用于一次选择多个监控区域，也支持运行中编辑已有区域。"""

    regions_selected = Signal(list)

    def __init__(
        self,
        screen_geometry: QRect,
        parent: QWidget | None = None,
        regions: list[QRect] | None = None,
        enabled: list[bool] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("选择监控区域")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setGeometry(screen_geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        self.regions = [QRect(rect) for rect in (regions or [])]
        self.enabled = list(enabled or [True] * len(self.regions))
        if len(self.enabled) < len(self.regions):
            self.enabled.extend([True] * (len(self.regions) - len(self.enabled)))
        self.active_index = -1
        self.hover_index = -1
        self.hover_action = ""
        self.hover_edges: set[str] = set()
        self.action = ""
        self.resize_edges: set[str] = set()
        self.start_point: QPoint | None = None
        self.origin_rect: QRect | None = None
        self.preview_rect: QRect | None = None
        # 四角方块用于斜向缩放，四边中点圆形控制点用于整体移动。
        self.handle_size = 8
        self.minimum_region_size = 20

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.grabKeyboard()

    def closeEvent(self, event) -> None:
        self.releaseKeyboard()
        super().closeEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 145))

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        for region in self.regions:
            painter.fillRect(region, Qt.GlobalColor.transparent)
        if self.preview_rect is not None:
            painter.fillRect(self.preview_rect, Qt.GlobalColor.transparent)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(
            20,
            34,
            "空白处拖动新增；拖动边中圆点移动；拖动四角方块缩放；Space 启用/停用；Delete 删除；Enter 完成；Esc 取消",
        )

        colors = [
            QColor(0, 210, 255),
            QColor(255, 190, 60),
            QColor(120, 255, 150),
            QColor(220, 140, 255),
        ]
        for index, region in enumerate(self.regions):
            color = colors[index % len(colors)]
            if not self.enabled[index]:
                color = QColor(140, 150, 165)
            if index == self.active_index:
                color = QColor(255, 255, 255)
            painter.setPen(QPen(color, 2))
            # 上一个区域的圆点使用了黄色填充；画新区域边框前必须关闭填充，
            # 否则第二个及后续区域会被黄色画刷整块填满。
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(region)
            painter.fillRect(
                QRect(region.left(), region.top(), 54, 22),
                QColor(10, 15, 25, 210),
            )
            painter.setPen(color)
            label = f"区域 {index + 1}"
            if not self.enabled[index]:
                label += "（停用）"
            painter.drawText(region.left() + 7, region.top() + 16, label)

            painter.setPen(QPen(color, 1))
            painter.setBrush(QColor(255, 255, 255, 235))
            for handle in self.corner_handle_rects(region).values():
                painter.drawRect(handle)
            painter.setBrush(QColor(255, 205, 70, 240))
            for handle in self.move_handle_rects(region):
                painter.drawEllipse(handle)

        if self.preview_rect is not None:
            painter.setPen(QPen(QColor(255, 255, 255), 2, Qt.PenStyle.DashLine))
            # 预览框只画虚线边框，不能继承前一个移动圆点的黄色填充。
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.preview_rect)

    def corner_handle_rects(self, region: QRect) -> dict[str, QRect]:
        """返回位于区域四角、用于斜向缩放的方形控制点。"""
        half = self.handle_size // 2
        size = self.handle_size
        return {
            "left|top": QRect(region.left() - half, region.top() - half, size, size),
            "right|top": QRect(region.right() - half, region.top() - half, size, size),
            "left|bottom": QRect(region.left() - half, region.bottom() - half, size, size),
            "right|bottom": QRect(region.right() - half, region.bottom() - half, size, size),
        }

    def move_handle_rects(self, region: QRect) -> list[QRect]:
        """返回位于四边中点、用于整体移动的圆形控制点。"""
        size = self.handle_size
        half = size // 2
        centers = [
            QPoint(region.center().x(), region.top()),
            QPoint(region.right(), region.center().y()),
            QPoint(region.center().x(), region.bottom()),
            QPoint(region.left(), region.center().y()),
        ]
        return [
            QRect(point.x() - half, point.y() - half, size, size)
            for point in centers
        ]

    def control_at(self, region: QRect, position: QPoint) -> tuple[str, set[str]]:
        # 小区域的控制点可能重叠，此时角点缩放优先。
        for edge_text, handle in self.corner_handle_rects(region).items():
            if handle.contains(position):
                return "resize", set(edge_text.split("|"))
        for handle in self.move_handle_rects(region):
            if handle.contains(position):
                return "move", set()
        return "", set()

    def hit_test(self, position: QPoint) -> tuple[int, str, set[str]]:
        # 重叠区域只允许最上层的一个区域响应。
        for index in range(len(self.regions) - 1, -1, -1):
            region = self.regions[index]
            if region.contains(position):
                action, edges = self.control_at(region, position)
                return index, action or "select", edges

        # 控制点以边框为中心，因此一半可能位于区域外部。
        for index in range(len(self.regions) - 1, -1, -1):
            action, edges = self.control_at(self.regions[index], position)
            if action:
                return index, action, edges
        return -1, "", set()

    def update_hover(self, position: QPoint) -> None:
        self.hover_index, self.hover_action, self.hover_edges = self.hit_test(position)
        if self.hover_action == "resize":
            if self.hover_edges in ({"left", "top"}, {"right", "bottom"}):
                cursor = Qt.CursorShape.SizeFDiagCursor
            else:
                cursor = Qt.CursorShape.SizeBDiagCursor
        elif self.hover_action == "move":
            cursor = Qt.CursorShape.SizeAllCursor
        elif self.hover_action == "select":
            cursor = Qt.CursorShape.ArrowCursor
        else:
            cursor = Qt.CursorShape.CrossCursor
        self.setCursor(cursor)
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        position = event.position().toPoint()
        index, action, edges = self.hit_test(position)
        if index < 0:
            self.active_index = -1
            self.action = "new"
            self.start_point = position
            self.preview_rect = QRect(position, position)
        else:
            self.active_index = index
            if action in ("move", "resize"):
                self.action = action
                self.start_point = position
                self.origin_rect = QRect(self.regions[index])
                self.resize_edges = edges
            else:
                # 区域内部只负责选中，不再触发移动。
                self.action = ""
                self.start_point = None
                self.origin_rect = None
                self.resize_edges.clear()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.start_point is None:
            self.update_hover(event.position().toPoint())
            return
        position = event.position().toPoint()
        delta = position - self.start_point
        if self.action == "new":
            self.preview_rect = QRect(self.start_point, position).normalized()
        elif self.action == "move" and self.origin_rect is not None:
            self.regions[self.active_index] = self.clamp_moved_rect(
                self.origin_rect.translated(delta)
            )
        elif self.action == "resize" and self.origin_rect is not None:
            self.regions[self.active_index] = self.resize_rect(
                self.origin_rect, delta, self.resize_edges
            )
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self.start_point is None:
            return
        if self.action == "new" and self.preview_rect is not None:
            if (
                self.preview_rect.width() >= self.minimum_region_size
                and self.preview_rect.height() >= self.minimum_region_size
            ):
                self.regions.append(QRect(self.preview_rect))
                self.enabled.append(True)
                self.active_index = len(self.regions) - 1
        self.action = ""
        self.resize_edges.clear()
        self.start_point = None
        self.origin_rect = None
        self.preview_rect = None
        self.update_hover(event.position().toPoint())
        self.update()

    def clamp_moved_rect(self, rect: QRect) -> QRect:
        x = max(0, min(rect.x(), self.width() - rect.width()))
        y = max(0, min(rect.y(), self.height() - rect.height()))
        return QRect(x, y, rect.width(), rect.height())

    def resize_rect(self, origin: QRect, delta: QPoint, edges: set[str]) -> QRect:
        left = origin.left()
        right = origin.right()
        top = origin.top()
        bottom = origin.bottom()
        if "left" in edges:
            left = max(0, min(origin.left() + delta.x(), right - self.minimum_region_size + 1))
        if "right" in edges:
            right = min(self.width() - 1, max(origin.right() + delta.x(), left + self.minimum_region_size - 1))
        if "top" in edges:
            top = max(0, min(origin.top() + delta.y(), bottom - self.minimum_region_size + 1))
        if "bottom" in edges:
            bottom = min(self.height() - 1, max(origin.bottom() + delta.y(), top + self.minimum_region_size - 1))
        return QRect(QPoint(left, top), QPoint(right, bottom)).normalized()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.reject()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.regions:
                self.regions_selected.emit([QRect(region) for region in self.regions])
                self.accept()
            return
        if event.key() == Qt.Key.Key_Delete and 0 <= self.active_index < len(self.regions):
            self.regions.pop(self.active_index)
            self.enabled.pop(self.active_index)
            self.active_index = min(self.active_index, len(self.regions) - 1)
            self.update()
            return
        if event.key() == Qt.Key.Key_Space and 0 <= self.active_index < len(self.regions):
            self.enabled[self.active_index] = not self.enabled[self.active_index]
            self.update()
            return
        super().keyPressEvent(event)

class TranslationWorker(QThread):
    completed = Signal(str, str)
    failed = Signal(str)
    no_text = Signal()
    unchanged = Signal(str)

    def __init__(self, image: Image.Image, settings: AppSettings, skip_text: str = ""):
        super().__init__()
        self.image = image
        self.settings = settings
        self.skip_text = skip_text

    def run(self) -> None:
        try:
            text = recognize_english(self.image, self.settings.tesseract_path)
            if not text:
                self.no_text.emit()
                return
            if self.skip_text and text == self.skip_text:
                self.unchanged.emit(text)
                return

            if "mymemory.translated.net" in self.settings.translation_url:
                target_language = self.settings.target_language
                if target_language == "zh":
                    target_language = "zh-CN"
                response = requests.get(
                    self.settings.translation_url,
                    params={
                        "q": text,
                        "langpair": f"{self.settings.source_language}|{target_language}",
                    },
                    timeout=30,
                )
            else:
                payload = {
                    "q": text,
                    "source": self.settings.source_language,
                    "target": self.settings.target_language,
                    "format": "text",
                }
                if self.settings.translation_api_key:
                    payload["api_key"] = self.settings.translation_api_key
                response = requests.post(self.settings.translation_url, json=payload, timeout=30)

            if not response.ok:
                try:
                    error_data = response.json()
                    error_message = error_data.get("error", "")
                except ValueError:
                    error_message = response.text.strip()
                detail = f"：{error_message}" if error_message else ""
                raise RuntimeError(f"翻译接口返回 HTTP {response.status_code}{detail}")
            data = response.json()
            if "mymemory.translated.net" in self.settings.translation_url:
                translated = data.get("responseData", {}).get("translatedText", "")
                if data.get("responseStatus") not in (None, 200):
                    raise RuntimeError(data.get("responseDetails", "MyMemory 翻译失败"))
                translated = html.unescape(translated).strip()
            else:
                translated = data.get("translatedText", "").strip()
            if not translated:
                raise RuntimeError("翻译接口没有返回翻译结果，请检查接口地址或文本长度。")
            self.completed.emit(text, translated)
        except pytesseract.TesseractNotFoundError:
            self.failed.emit("找不到 Tesseract。请安装 Tesseract，或在设置中填写 tesseract.exe 的完整路径。")
        except requests.RequestException as exc:
            self.failed.emit(f"翻译请求失败：{exc}")
        except Exception as exc:  # noqa: BLE001 - 将第三方错误展示给用户
            self.failed.emit(str(exc))


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


class MonitorResultWindow(QDialog):
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
        # 翻译悬浮窗固定为默认尺寸，避免后续出现边框缩放和布局互相影响。
        self.setFixedSize(520, 220)

        self.card = QWidget(self)
        self.card.setObjectName("resultCard")
        self.card.setMouseTracking(True)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 150))
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
        self.scroll_direction = 1
        self.display_revision = 0
        self.pending_scroll_state: tuple[int, bool, int] | None = None

        # 子控件（标题栏、滚动区域、文字标签）会分别接收鼠标事件。
        # 在每个子控件上安装过滤器会导致坐标系和事件处理顺序不一致，
        # 所以改成由 QApplication 统一观察本窗口及其所有子控件。
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def update_result(self, original: str, translated: str) -> None:
        cleaned = compact_display_text(translated)
        self.set_display_entries([(None, cleaned)] if cleaned else [])

    def update_regions(self, regions: list[tuple[int, str]]) -> None:
        """在同一个滚动内容中显示所有区域的紧凑译文。"""
        entries = []
        for region_id, translated in regions:
            cleaned = compact_display_text(translated)
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
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            card_layout.setSpacing(2)

            if region_id is not None:
                header = QLabel(f"区域 {region_id + 1}", card)
                header.setObjectName("resultRegionHeader")
                card_layout.addWidget(header)

            body = QLabel(text, card)
            body.setObjectName("resultTranslation")
            body.setWordWrap(True)
            body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            body.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            )
            body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            body.setAutoFillBackground(False)
            card_layout.addWidget(body)
            self.translation_cards_layout.addWidget(card)
            self.translation_cards.append((card, body))

        self.show()
        self.raise_()
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
        selected_font.setPointSize(self.translation_font_size)
        for _card, body in self.translation_cards:
            body.setFont(selected_font)
            body.updateGeometry()
        self.translation_content.adjustSize()
        self.translation_scroll.updateGeometry()
        QTimer.singleShot(0, lambda rev=revision: self.restore_scroll_after_update(rev))

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
        if maximum > 0 and self.isVisible():
            self.scroll_pause_timer.start(1200)

    def restart_auto_scroll(self) -> None:
        self.scroll_timer.stop()
        self.scroll_pause_timer.stop()
        scrollbar = self.translation_scroll.verticalScrollBar()
        scrollbar.setValue(0)
        self.scroll_direction = 1
        if scrollbar.maximum() > 0 and self.isVisible():
            self.scroll_pause_timer.start(1200)

    def start_auto_scroll(self) -> None:
        scrollbar = self.translation_scroll.verticalScrollBar()
        if scrollbar.maximum() > 0 and self.isVisible():
            self.scroll_timer.start()

    def auto_scroll_step(self) -> None:
        scrollbar = self.translation_scroll.verticalScrollBar()
        maximum = scrollbar.maximum()
        if maximum <= 0 or not self.isVisible():
            self.scroll_timer.stop()
            return
        next_value = scrollbar.value() + self.scroll_direction
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
            f"QWidget#resultCard {{ background: rgba(20, 25, 38, {background_alpha}); "
            f"border: 1px solid rgba(120, 180, 255, {border_alpha}); border-radius: 16px; }}"
            "QWidget#resultTitleBar { background: transparent; }"
            f"QLabel#resultTitle {{ color: rgba(219, 234, 254, {chrome_alpha}); font-size: 12px; font-weight: 600; }}"
            f"QLabel#resultLockState {{ color: rgba(125, 211, 252, {chrome_alpha}); font-size: 10px; font-weight: 700; }}"
            f"QFrame#translationCard {{ background: rgba(15, 23, 42, {mask_alpha}); border-radius: 8px; }}"
            f"QLabel#resultRegionHeader {{ color: rgba(125, 211, 252, {text_alpha}); font-size: 10px; font-weight: 700; }}"
            f"QLabel#resultTranslation {{ color: rgba(248, 250, 252, {text_alpha}); padding: 1px; }}"
            "QScrollArea, QScrollArea > QWidget { background: transparent; border: none; }"
            "QScrollArea > QWidget#qt_scrollarea_viewport { background: transparent; }"
            "QScrollBar:vertical { background: rgba(255,255,255,25); width: 6px; }"
            "QScrollBar::handle:vertical { background: rgba(150,200,255,150); "
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
        if not self.is_result_widget(watched):
            return super().eventFilter(watched, event)
        if self.locked:
            return super().eventFilter(watched, event)

        # QApplication 级过滤器能拿到所有子控件的鼠标事件。
        # 悬浮窗没有按钮，因此解锁时整个窗口都可用于拖动位置。
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self.drag_start = event.globalPosition().toPoint()
                self.drag_origin = self.frameGeometry().topLeft()
                return True
        elif event.type() == QEvent.Type.MouseMove:
            global_position = event.globalPosition().toPoint()
            if self.drag_start is not None and self.drag_origin is not None:
                self.move(self.drag_origin + global_position - self.drag_start)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                self.drag_start = None
                self.drag_origin = None
                return True
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
        width = 520
        height = 220
        self.setFixedSize(width, height)
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

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084:  # WM_NCHITTEST
                    if self.locked:
                        return True, -1  # HTTRANSPARENT: 鼠标事件穿透到下方窗口
            except (TypeError, ValueError):
                pass
        return super().nativeEvent(event_type, message)

    def closeEvent(self, event) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.scroll_timer.stop()
        self.scroll_pause_timer.stop()
        self.stop_requested.emit()
        super().closeEvent(event)

    def hideEvent(self, event) -> None:
        self.scroll_timer.stop()
        self.scroll_pause_timer.stop()
        super().hideEvent(event)


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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.worker: TranslationWorker | None = None
        self.monitor_workers: dict[tuple[int, int], TranslationWorker] = {}
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.monitor_tick)
        self.monitor_active = False
        self.monitor_screen = None
        self.monitor_regions: list[MonitorRegion] = []
        self.monitor_interval_ms = 2000
        self.monitor_generation = 0
        self.monitor_editing = False
        self.monitor_edit_previous_lock = False
        self.capture_active = False
        self.hotkey_filter: GlobalHotkeyFilter | None = None
        self.setWindowTitle("Screen Translator")
        self.resize(760, 560)

        self.start_button = QPushButton("截图翻译")
        self.start_button.setMinimumHeight(42)
        self.start_button.clicked.connect(self.start_capture)
        self.settings_button = QPushButton("设置")
        self.settings_button.clicked.connect(self.open_settings)
        self.monitor_button = QPushButton("开始持续监控")
        self.monitor_button.setMinimumHeight(42)
        self.monitor_button.clicked.connect(self.start_monitor)
        self.overlay_lock_button = QPushButton("锁定翻译窗口")
        self.overlay_lock_button.setEnabled(False)
        self.overlay_lock_button.clicked.connect(self.toggle_overlay_lock)
        self.manage_regions_button = QPushButton("管理监控区域")
        self.manage_regions_button.setEnabled(False)
        self.manage_regions_button.clicked.connect(self.manage_monitor_regions)
        self.monitor_result_window = MonitorResultWindow()
        self.monitor_result_window.stop_requested.connect(self.stop_monitor)
        self.monitor_result_window.lock_changed.connect(self.sync_overlay_lock_button)
        self.background_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.background_opacity_slider.setRange(0, 100)
        self.background_opacity_slider.setValue(
            max(0, min(100, self.settings.overlay_opacity))
        )
        self.background_opacity_slider.valueChanged.connect(self.set_overlay_opacity)
        self.background_opacity_value_label = QLabel(
            f"{self.background_opacity_slider.value()}%"
        )
        self.background_opacity_value_label.setObjectName("opacityLabel")
        background_opacity_row = QHBoxLayout()
        background_opacity_row.addWidget(QLabel("窗口背景不透明度"))
        background_opacity_row.addWidget(self.background_opacity_slider, 1)
        background_opacity_row.addWidget(self.background_opacity_value_label)

        self.text_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.text_opacity_slider.setRange(30, 100)
        self.text_opacity_slider.setValue(
            max(30, min(100, self.settings.overlay_text_opacity))
        )
        self.text_opacity_slider.valueChanged.connect(self.set_overlay_text_opacity)
        self.text_opacity_value_label = QLabel(
            f"{self.text_opacity_slider.value()}%"
        )
        self.text_opacity_value_label.setObjectName("opacityLabel")
        text_opacity_row = QHBoxLayout()
        text_opacity_row.addWidget(QLabel("翻译文字不透明度"))
        text_opacity_row.addWidget(self.text_opacity_slider, 1)
        text_opacity_row.addWidget(self.text_opacity_value_label)

        self.mask_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.mask_opacity_slider.setRange(0, 100)
        self.mask_opacity_slider.setValue(
            max(0, min(100, self.settings.overlay_mask_opacity))
        )
        self.mask_opacity_slider.valueChanged.connect(self.set_overlay_mask_opacity)
        self.mask_opacity_value_label = QLabel(
            f"{self.mask_opacity_slider.value()}%"
        )
        self.mask_opacity_value_label.setObjectName("opacityLabel")
        mask_opacity_row = QHBoxLayout()
        mask_opacity_row.addWidget(QLabel("文字蒙版不透明度"))
        mask_opacity_row.addWidget(self.mask_opacity_slider, 1)
        mask_opacity_row.addWidget(self.mask_opacity_value_label)

        self.font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setRange(9, 28)
        self.font_size_slider.setValue(
            max(9, min(28, self.settings.overlay_font_size))
        )
        self.font_size_slider.valueChanged.connect(self.set_overlay_font_size)
        self.font_size_value_label = QLabel(f"{self.font_size_slider.value()} pt")
        self.font_size_value_label.setObjectName("opacityLabel")
        font_size_row = QHBoxLayout()
        font_size_row.addWidget(QLabel("翻译字体大小"))
        font_size_row.addWidget(self.font_size_slider, 1)
        font_size_row.addWidget(self.font_size_value_label)

        self.monitor_result_window.set_background_opacity(
            self.background_opacity_slider.value()
        )
        self.monitor_result_window.set_text_opacity(self.text_opacity_slider.value())
        self.monitor_result_window.set_mask_opacity(self.mask_opacity_slider.value())
        self.monitor_result_window.set_translation_font_size(self.font_size_slider.value())

        self.status_label = QLabel("准备就绪。点击“截图翻译”后框选英文区域。")
        self.status_label.setObjectName("statusLabel")
        self.original_edit = QPlainTextEdit()
        self.original_edit.setReadOnly(True)
        self.original_edit.setPlaceholderText("OCR 识别出的英文会显示在这里")
        self.translated_edit = QPlainTextEdit()
        self.translated_edit.setReadOnly(True)
        self.translated_edit.setPlaceholderText("中文翻译会显示在这里")

        original_box = QGroupBox("识别结果")
        original_layout = QVBoxLayout(original_box)
        original_layout.addWidget(self.original_edit)
        translated_box = QGroupBox("翻译结果")
        translated_layout = QVBoxLayout(translated_box)
        translated_layout.addWidget(self.translated_edit)

        top = QVBoxLayout()
        top.addWidget(self.start_button)
        top.addWidget(self.monitor_button)
        top.addWidget(self.manage_regions_button)
        top.addWidget(self.overlay_lock_button)
        top.addWidget(self.settings_button)
        top.addLayout(background_opacity_row)
        top.addLayout(text_opacity_row)
        top.addLayout(mask_opacity_row)
        top.addLayout(font_size_row)
        top.addWidget(self.status_label)

        body = QWidget()
        body.setObjectName("mainRoot")
        layout = QVBoxLayout(body)
        layout.addLayout(top)
        layout.addWidget(original_box)
        layout.addWidget(translated_box)
        self.setCentralWidget(body)
        self.setStyleSheet(MAIN_STYLE_SHEET)

        try:
            self.hotkey_filter = GlobalHotkeyFilter(
                self.winId(), self.settings.hotkey, self.start_capture
            )
            QApplication.instance().installNativeEventFilter(self.hotkey_filter)
            self.status_label.setText(
                f"准备就绪。点击“截图翻译”或按 {self.settings.hotkey}，然后框选英文区域。"
            )
        except (RuntimeError, ValueError) as exc:
            self.status_label.setText(f"热键不可用：{exc}")

    def open_settings(self) -> None:
        old_hotkey = self.settings.hotkey
        if SettingsDialog(self.settings, self).exec() != QDialog.DialogCode.Accepted:
            return
        if self.settings.hotkey == old_hotkey:
            return
        self.unregister_hotkey()
        try:
            self.register_hotkey()
        except (RuntimeError, ValueError) as exc:
            self.settings.hotkey = old_hotkey
            save_settings(self.settings)
            try:
                self.register_hotkey()
            except (RuntimeError, ValueError):
                pass
            QMessageBox.warning(self, "热键设置失败", str(exc))

    def register_hotkey(self) -> None:
        self.hotkey_filter = GlobalHotkeyFilter(
            self.winId(), self.settings.hotkey, self.start_capture
        )
        QApplication.instance().installNativeEventFilter(self.hotkey_filter)
        self.status_label.setText(
            f"准备就绪。点击“截图翻译”或按 {self.settings.hotkey}，然后框选英文区域。"
        )

    def unregister_hotkey(self) -> None:
        if self.hotkey_filter is not None:
            QApplication.instance().removeNativeEventFilter(self.hotkey_filter)
            self.hotkey_filter.unregister()
            self.hotkey_filter = None

    def start_capture(self) -> None:
        if self.capture_active:
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.show_error("找不到可用的屏幕。")
            return
        self.capture_active = True
        self.hide()
        overlay = CaptureOverlay(screen.geometry())
        overlay.selected.connect(lambda rect: self.capture_finished(screen, rect, overlay))
        overlay.finished.connect(self.capture_overlay_finished)
        overlay.show()
        overlay.exec()

    def start_monitor(self) -> None:
        if self.monitor_active:
            self.stop_monitor()
            return
        if any(worker.isRunning() for worker in self.monitor_workers.values()):
            QMessageBox.information(self, "持续监控", "上一轮识别还没有结束，请稍候再启动。")
            return
        dialog = MonitorSetupDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.show_error("找不到可用的屏幕。")
            return
        interval_ms = max(500, round(dialog.interval_seconds * 1000))
        if dialog.monitor_full_screen:
            geometry = screen.geometry()
            full_rect = QRect(0, 0, geometry.width(), geometry.height())
            self.begin_monitor(screen, [full_rect], interval_ms)
            return

        self.capture_active = True
        self.hide()
        overlay = MultiRegionOverlay(
            screen.geometry(),
        )
        overlay.regions_selected.connect(
            lambda rects: self.monitor_region_selected(
                screen, rects, overlay, interval_ms
            )
        )
        overlay.finished.connect(self.capture_overlay_finished)
        overlay.show()
        overlay.exec()

    def monitor_region_selected(
        self, screen, rects: list[QRect], overlay: MultiRegionOverlay, interval_ms: int
    ) -> None:
        overlay.hide()
        # 让遮罩层的隐藏操作先提交到窗口系统，避免第一次监控截图
        # 仍然截到半透明的框选层。
        QApplication.processEvents()
        self.begin_monitor(screen, rects, interval_ms, overlay.enabled)

    def begin_monitor(
        self,
        screen,
        rects: list[QRect],
        interval_ms: int,
        enabled: list[bool] | None = None,
    ) -> None:
        self.monitor_active = True
        self.monitor_screen = screen
        enabled_values = enabled or [True] * len(rects)
        self.monitor_regions = [
            MonitorRegion(QRect(rect), enabled=enabled_values[index])
            for index, rect in enumerate(rects)
        ]
        self.monitor_interval_ms = interval_ms
        self.monitor_generation += 1
        self.monitor_button.setText("停止持续监控")
        self.manage_regions_button.setEnabled(True)
        self.overlay_lock_button.setEnabled(True)
        self.status_label.setText(
            f"持续监控中，共 {len(self.monitor_regions)} 个区域，每 {interval_ms / 1000:g} 秒检查一次。"
        )
        self.monitor_result_window.set_locked(False)
        self.monitor_result_window.restore_geometry(self.settings, screen.geometry())
        self.monitor_result_window.clear_result()
        self.monitor_result_window.show()
        self.monitor_timer.start(interval_ms)
        self.monitor_tick()

    def manage_monitor_regions(self) -> None:
        if not self.monitor_active or self.monitor_screen is None or self.monitor_editing:
            return
        self.monitor_editing = True
        self.monitor_timer.stop()
        self.monitor_generation += 1
        self.monitor_edit_previous_lock = self.monitor_result_window.locked
        self.monitor_result_window.set_locked(True)

        overlay = MultiRegionOverlay(
            self.monitor_screen.geometry(),
            self,
            [region.rect for region in self.monitor_regions],
            [region.enabled for region in self.monitor_regions],
        )
        overlay.regions_selected.connect(
            lambda rects: self.monitor_regions_selected(rects, overlay)
        )
        overlay.finished.connect(self.monitor_region_editor_finished)
        overlay.show()
        overlay.exec()

    def monitor_regions_selected(
        self, rects: list[QRect], overlay: MultiRegionOverlay
    ) -> None:
        if not rects:
            return
        overlay.hide()
        QApplication.processEvents()
        self.monitor_regions = [
            MonitorRegion(QRect(rect), enabled=overlay.enabled[index])
            for index, rect in enumerate(rects)
        ]
        self.monitor_editing = False
        self.monitor_generation += 1
        self.monitor_result_window.set_locked(self.monitor_edit_previous_lock)
        self.refresh_monitor_result_window()
        self.status_label.setText(
            f"持续监控中，已更新为 {len(self.monitor_regions)} 个区域。"
        )
        self.monitor_timer.start(self.monitor_interval_ms)
        self.monitor_tick()

    def monitor_region_editor_finished(self, _code: int) -> None:
        if not self.monitor_editing:
            return
        self.monitor_editing = False
        self.monitor_result_window.set_locked(self.monitor_edit_previous_lock)
        self.monitor_generation += 1
        self.monitor_timer.start(self.monitor_interval_ms)
        self.status_label.setText("持续监控中，区域没有修改。")
        self.monitor_tick()

    def stop_monitor(self) -> None:
        if not self.monitor_active and not self.monitor_timer.isActive():
            return
        self.monitor_active = False
        self.monitor_editing = False
        self.monitor_generation += 1
        self.monitor_timer.stop()
        self.monitor_result_window.save_geometry(self.settings)
        self.monitor_result_window.set_locked(False)
        save_settings(self.settings)
        self.monitor_result_window.hide()
        self.monitor_button.setText("开始持续监控")
        self.manage_regions_button.setEnabled(False)
        self.overlay_lock_button.setEnabled(False)
        self.status_label.setText("持续监控已停止。")

    def toggle_overlay_lock(self) -> None:
        if self.monitor_active:
            self.monitor_result_window.set_locked(not self.monitor_result_window.locked)

    def set_overlay_opacity(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self.background_opacity_value_label.setText(f"{value}%")
        self.monitor_result_window.set_background_opacity(value)
        self.settings.overlay_opacity = value
        save_settings(self.settings)

    def set_overlay_text_opacity(self, value: int) -> None:
        value = max(30, min(100, int(value)))
        self.text_opacity_value_label.setText(f"{value}%")
        self.monitor_result_window.set_text_opacity(value)
        self.settings.overlay_text_opacity = value
        save_settings(self.settings)

    def set_overlay_mask_opacity(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self.mask_opacity_value_label.setText(f"{value}%")
        self.monitor_result_window.set_mask_opacity(value)
        self.settings.overlay_mask_opacity = value
        save_settings(self.settings)

    def set_overlay_font_size(self, value: int) -> None:
        value = max(9, min(28, int(value)))
        self.font_size_value_label.setText(f"{value} pt")
        self.monitor_result_window.set_translation_font_size(value)
        self.settings.overlay_font_size = value
        save_settings(self.settings)

    def sync_overlay_lock_button(self, locked: bool) -> None:
        self.overlay_lock_button.setText(
            "解锁翻译窗口" if locked else "锁定翻译窗口"
        )

    def monitor_tick(self) -> None:
        if (
            not self.monitor_active
            or self.monitor_editing
            or self.monitor_screen is None
        ):
            return
        generation = self.monitor_generation
        for region_id, region in enumerate(self.monitor_regions):
            worker_key = (generation, region_id)
            if not region.enabled or worker_key in self.monitor_workers:
                continue
            try:
                image = self.capture_region(self.monitor_screen, region.rect)
            except Exception as exc:  # noqa: BLE001 - 将截图后端错误展示给用户
                self.monitor_failed(
                    f"区域 {region_id + 1} 截图失败：{exc}",
                    generation,
                )
                continue

            worker = TranslationWorker(image, self.settings, region.last_text)
            self.monitor_workers[worker_key] = worker
            worker.completed.connect(
                lambda original, translated, rid=region_id, g=generation: self.monitor_result(
                    rid, original, translated, g
                )
            )
            worker.unchanged.connect(
                lambda _text, rid=region_id, g=generation: self.monitor_unchanged(
                    rid, g
                )
            )
            worker.no_text.connect(
                lambda rid=region_id, g=generation: self.monitor_no_text(rid, g)
            )
            worker.failed.connect(
                lambda message, rid=region_id, g=generation: self.monitor_failed(
                    f"区域 {rid + 1}：{message}", g
                )
            )
            worker.finished.connect(lambda w=worker: self.monitor_worker_finished(w))
            worker.start()

    def monitor_worker_finished(self, worker: TranslationWorker) -> None:
        for region_id, active_worker in list(self.monitor_workers.items()):
            if active_worker is worker:
                self.monitor_workers.pop(region_id, None)
                break
        worker.deleteLater()

    def monitor_result(
        self, region_id: int, original: str, translated: str, generation: int
    ) -> None:
        if not self.monitor_active or generation != self.monitor_generation:
            return
        if region_id >= len(self.monitor_regions):
            return
        region = self.monitor_regions[region_id]
        region.last_text = original
        region.translated = translated
        self.refresh_monitor_result_window()
        self.status_label.setText(f"持续监控中：区域 {region_id + 1} 发现新的英文内容。")

    def monitor_unchanged(self, region_id: int, generation: int) -> None:
        if self.monitor_active and generation == self.monitor_generation:
            self.status_label.setText(f"持续监控中：区域 {region_id + 1} 文字没有变化。")

    def monitor_no_text(self, region_id: int, generation: int) -> None:
        if self.monitor_active and generation == self.monitor_generation:
            if region_id < len(self.monitor_regions):
                self.monitor_regions[region_id].last_text = ""
                self.monitor_regions[region_id].translated = ""
                self.refresh_monitor_result_window()
            self.status_label.setText(
                f"持续监控中：区域 {region_id + 1} 没有检测到英文。"
            )

    def monitor_failed(self, message: str, generation: int) -> None:
        if self.monitor_active and generation == self.monitor_generation:
            self.status_label.setText(f"持续监控错误：{message}")

    def refresh_monitor_result_window(self) -> None:
        regions = []
        for index, region in enumerate(self.monitor_regions):
            if region.enabled and region.translated:
                regions.append((index, region.translated))
        if regions:
            self.monitor_result_window.update_regions(regions)
        else:
            self.monitor_result_window.clear_result()

    def capture_overlay_finished(self, _code: int) -> None:
        self.capture_active = False
        self.show()
        self.activateWindow()

    def capture_finished(self, screen, rect: QRect, overlay: CaptureOverlay) -> None:
        overlay.hide()
        QApplication.processEvents()
        try:
            image = self.capture_region(screen, rect)
        except Exception as exc:  # noqa: BLE001 - 将截图后端错误展示给用户
            self.show_error(f"截图失败：{exc}")
            return
        self.original_edit.clear()
        self.translated_edit.clear()
        self.status_label.setText("正在识别和翻译，请稍候……")
        self.start_button.setEnabled(False)
        self.worker = TranslationWorker(image, self.settings)
        self.worker.completed.connect(self.show_result)
        self.worker.no_text.connect(
            lambda: self.show_error("没有识别到英文，请尝试扩大区域或提高文字清晰度。")
        )
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(lambda: self.start_button.setEnabled(True))
        self.worker.start()

    def capture_region(self, screen, rect: QRect) -> Image.Image:
        dpr = screen.devicePixelRatio()
        screen_geometry = screen.geometry()
        monitor = {
            "left": round((screen_geometry.x() + rect.x()) * dpr),
            "top": round((screen_geometry.y() + rect.y()) * dpr),
            "width": max(1, round(rect.width() * dpr)),
            "height": max(1, round(rect.height() * dpr)),
        }
        with MSS() as screen_capture:
            shot = screen_capture.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.rgb)

    def show_result(self, original: str, translated: str) -> None:
        self.original_edit.setPlainText(original)
        self.translated_edit.setPlainText(translated)
        self.status_label.setText("完成。")

    def show_error(self, message: str) -> None:
        self.status_label.setText("处理失败。")
        self.start_button.setEnabled(True)
        QMessageBox.warning(self, "Screen Translator", message)

    def closeEvent(self, event) -> None:
        self.stop_monitor()
        self.monitor_result_window.close()
        self.unregister_hotkey()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
