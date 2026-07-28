import unittest

from screen_translator.languages import (
    detect_language,
    language_display_label,
    normalize_qwen_code,
    qwen_language_name,
    qwen_language_options,
    tesseract_language_for_source,
)


class LanguageTests(unittest.TestCase):
    def test_detect_language_handles_common_scripts(self) -> None:
        self.assertEqual(detect_language("这是中文"), "zh-CN")
        self.assertEqual(detect_language("これは日本語です"), "ja")
        self.assertEqual(detect_language("한국어 문장"), "ko")
        self.assertEqual(detect_language("Hello, this is a test"), "en")
        self.assertEqual(detect_language("Hola"), "es")

    def test_language_display_label_handles_auto_and_unknown(self) -> None:
        self.assertEqual(language_display_label("auto"), "自动检测")
        self.assertEqual(language_display_label("unknown"), "未识别")

    def test_qwen_language_aliases_are_normalized(self) -> None:
        self.assertEqual(qwen_language_name("zh"), "Chinese")
        self.assertEqual(qwen_language_name("zh_tw"), "Traditional Chinese")
        self.assertEqual(normalize_qwen_code("en-US"), "en")

    def test_qwen_lite_excludes_extended_languages(self) -> None:
        all_codes = {
            code for code, _label, _name in qwen_language_options("qwen-mt-flash")
        }
        lite_codes = {
            code for code, _label, _name in qwen_language_options("qwen-mt-lite")
        }
        self.assertIn("yue", all_codes)
        self.assertNotIn("yue", lite_codes)
        self.assertNotIn("auto", lite_codes)

    def test_source_language_selects_matching_tesseract_model(self) -> None:
        self.assertEqual(tesseract_language_for_source("ja"), "jpn")
        self.assertEqual(tesseract_language_for_source("zh-CN"), "chi_sim")
        self.assertIn("jpn", tesseract_language_for_source("auto"))
