import unittest
from unittest.mock import patch

from PIL import Image

from screen_translator.ocr import recognize_text


class OcrTests(unittest.TestCase):
    def test_recognize_text_uses_selected_language(self) -> None:
        image = Image.new("RGB", (20, 20), "white")
        with (
            patch("screen_translator.ocr._configure_for_ocr"),
            patch("screen_translator.ocr._prepare_ocr_image", return_value=image),
            patch(
                "screen_translator.ocr.pytesseract.image_to_string",
                side_effect=["你好", ""],
            ) as image_to_string,
        ):
            self.assertEqual(recognize_text(image, language="chi_sim"), "你好")

        self.assertEqual(image_to_string.call_args.kwargs["lang"], "chi_sim")
