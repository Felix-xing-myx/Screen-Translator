import unittest

from screen_translator.hotkeys import hotkey_to_win32


class HotkeyTests(unittest.TestCase):
    def test_common_hotkey(self) -> None:
        modifiers, virtual_key = hotkey_to_win32("Ctrl+Shift+T")
        self.assertEqual(modifiers, 0x0002 | 0x0004)
        self.assertEqual(virtual_key, ord("T"))

    def test_modifier_is_required(self) -> None:
        with self.assertRaises(ValueError):
            hotkey_to_win32("T")

