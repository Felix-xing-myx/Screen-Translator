import unittest
from types import SimpleNamespace
from unittest.mock import patch

from screen_translator.config import AppSettings
from screen_translator.translator import split_text_for_translation, translate_text


class LongTranslatorTests(unittest.TestCase):
    def test_chunks_stay_within_limit(self) -> None:
        text = "alpha beta gamma delta"
        chunks = split_text_for_translation(text, max_chars=7)

        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= 7 for chunk in chunks))
        self.assertEqual(" ".join(chunks), text)

    def test_long_text_is_requested_in_order(self) -> None:
        requested: list[str] = []

        def fake_get(_url, params, timeout):
            self.assertEqual(timeout, 30)
            requested.append(params["q"])
            return SimpleNamespace(
                ok=True,
                status_code=200,
                text="",
                json=lambda: {
                    "responseData": {"translatedText": f"<{params['q']}>"},
                    "responseStatus": 200,
                },
            )

        with patch("screen_translator.translator.requests.get", side_effect=fake_get):
            translated = translate_text(
                "alpha beta gamma", AppSettings(), max_chars=7
            )

        self.assertEqual(requested, ["alpha", "beta", "gamma"])
        self.assertEqual(translated, "<alpha>\n<beta>\n<gamma>")

    def test_chunk_failure_contains_segment_context(self) -> None:
        calls = 0

        def fake_get(_url, params, timeout):
            nonlocal calls
            calls += 1
            if calls == 2:
                return SimpleNamespace(
                    ok=False,
                    status_code=400,
                    text="too long",
                    json=lambda: {},
                )
            return SimpleNamespace(
                ok=True,
                status_code=200,
                text="",
                json=lambda: {
                    "responseData": {"translatedText": params["q"]},
                    "responseStatus": 200,
                },
            )

        with patch("screen_translator.translator.requests.get", side_effect=fake_get):
            with self.assertRaisesRegex(RuntimeError, r"第 2/3 段翻译失败"):
                translate_text("alpha beta gamma", AppSettings(), max_chars=7)

