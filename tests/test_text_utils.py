import unittest

from screen_translator.text_utils import compact_display_text


class TextUtilsTests(unittest.TestCase):
    def test_compact_display_text(self) -> None:
        self.assertEqual(compact_display_text("  Hello\n\t world  "), "Hello world")

