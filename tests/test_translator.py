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

    def test_qwen_mt_uses_its_separate_key_and_translation_options(self) -> None:
        response = SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="你好")
                    )
                ]
            ),
        )
        settings = AppSettings(
            translation_provider="qwen_mt",
            translation_qwen_api_key="translation-key",
            dashscope_api_key="different-audio-key",
        )
        with patch(
            "dashscope.Generation.call", return_value=response
        ) as call:
            self.assertEqual(translate_text("hello", settings), "你好")

        call.assert_called_once()
        kwargs = call.call_args.kwargs
        self.assertEqual(kwargs["api_key"], "translation-key")
        self.assertEqual(kwargs["model"], "qwen-mt-flash")
        self.assertEqual(
            kwargs["translation_options"],
            {"source_lang": "English", "target_lang": "Chinese"},
        )

    def test_qwen_403_explains_free_quota_exhaustion(self) -> None:
        response = SimpleNamespace(status_code=403, code="Forbidden", message="quota")
        settings = AppSettings(
            translation_provider="qwen_mt",
            translation_qwen_api_key="translation-key",
        )
        with patch("dashscope.Generation.call", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "免费额度可能已用尽"):
                translate_text("hello", settings)
