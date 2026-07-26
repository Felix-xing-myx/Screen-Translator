import unittest

from screen_translator.text_utils import compact_display_text


class TextUtilsTests(unittest.TestCase):
    def test_compact_display_text(self) -> None:
        self.assertEqual(compact_display_text("  Hello\n\t world  "), "Hello world")

    def test_compact_display_text_can_preserve_translation_lines(self) -> None:
        self.assertEqual(
            compact_display_text(" first line \n second\tline ", preserve_lines=True),
            "first line\nsecond line",
        )
