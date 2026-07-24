import unittest
from types import SimpleNamespace
from unittest.mock import patch

from screen_translator.config import AppSettings
from screen_translator.translator import translate_text


class TranslatorTests(unittest.TestCase):
    def test_mymemory_response(self) -> None:
        response = SimpleNamespace(
            ok=True,
            status_code=200,
            text="",
            json=lambda: {
                "responseData": {"translatedText": "你好"},
                "responseStatus": 200,
            },
        )
        with patch("screen_translator.translator.requests.get", return_value=response):
            self.assertEqual(translate_text("hello", AppSettings()), "你好")

    def test_empty_response_is_rejected(self) -> None:
        response = SimpleNamespace(
            ok=True,
            status_code=200,
            text="",
            json=lambda: {"responseData": {"translatedText": ""}},
        )
        with patch("screen_translator.translator.requests.get", return_value=response):
            with self.assertRaises(RuntimeError):
                translate_text("hello", AppSettings())

