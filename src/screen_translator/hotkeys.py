"""Windows global hotkey support and the Qt hotkey editor widget."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QLineEdit, QWidget


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

    def __init__(self, hwnd: int, hotkey: str, callback, hotkey_id: int = HOTKEY_ID):
        super().__init__()
        self._hwnd = int(hwnd)
        self._callback = callback
        self._hotkey = hotkey
        self._hotkey_id = int(hotkey_id)
        modifiers, virtual_key = hotkey_to_win32(hotkey)
        self._user32 = ctypes.windll.user32
        self._registered = bool(
            self._user32.RegisterHotKey(
                self._hwnd,
                self._hotkey_id,
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
        if msg.message == self.WM_HOTKEY and msg.wParam == self._hotkey_id:
            self._callback()
            return True, 0
        return False, 0

    def unregister(self) -> None:
        if self._registered:
            self._user32.UnregisterHotKey(self._hwnd, self._hotkey_id)
            self._registered = False
