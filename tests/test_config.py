import os
import tempfile
import unittest
from unittest.mock import patch

from screen_translator.config import AppSettings, load_settings, save_settings


class ConfigTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"APPDATA": directory}):
                original = AppSettings(
                    target_language="ja",
                    overlay_font_size=18,
                    translation_provider="qwen_mt",
                    translation_qwen_api_key="translation-key",
                    dashscope_api_key="audio-key",
                    hotkey_enabled=False,
                    monitor_hotkey="Ctrl+Alt+M",
                    monitor_hotkey_enabled=True,
                    audio_hotkey="Ctrl+Alt+A",
                    audio_hotkey_enabled=True,
                )
                save_settings(original)
                loaded = load_settings()

        self.assertEqual(loaded.target_language, "ja")
        self.assertEqual(loaded.overlay_font_size, 18)
        self.assertEqual(loaded.translation_provider, "qwen_mt")
        self.assertEqual(loaded.translation_qwen_api_key, "translation-key")
        self.assertEqual(loaded.dashscope_api_key, "audio-key")
        self.assertFalse(loaded.hotkey_enabled)
        self.assertEqual(loaded.monitor_hotkey, "Ctrl+Alt+M")
        self.assertTrue(loaded.monitor_hotkey_enabled)
        self.assertEqual(loaded.audio_hotkey, "Ctrl+Alt+A")
        self.assertTrue(loaded.audio_hotkey_enabled)

    def test_invalid_json_returns_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"APPDATA": directory}):
                path = os.path.join(directory, "ScreenTranslator")
                os.makedirs(path)
                with open(os.path.join(path, "settings.json"), "w", encoding="utf-8") as handle:
                    handle.write("not-json")
                self.assertEqual(load_settings(), AppSettings())

    def test_malformed_field_types_fall_back_per_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"APPDATA": directory}):
                path = os.path.join(directory, "ScreenTranslator")
                os.makedirs(path)
                with open(os.path.join(path, "settings.json"), "w", encoding="utf-8") as handle:
                    handle.write(
                        '{"overlay_opacity":"bad", "audio_history_limit":[], '
                        '"hotkey_enabled":"yes", "target_language":"ja"}'
                    )

                loaded = load_settings()

        self.assertEqual(loaded.overlay_opacity, AppSettings().overlay_opacity)
        self.assertEqual(loaded.audio_history_limit, AppSettings().audio_history_limit)
        self.assertEqual(loaded.hotkey_enabled, AppSettings().hotkey_enabled)
        self.assertEqual(loaded.target_language, "ja")
