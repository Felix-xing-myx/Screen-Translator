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
                    overlay_scroll_speed=4,
                    translation_provider="qwen_mt",
                    translation_qwen_api_key="translation-key",
                    source_language="ja",
                    dashscope_api_key="audio-key",
                    audio_translation_model="custom",
                    audio_custom_translation_model_id="qwen3.5-custom-realtime",
                    hotkey_enabled=False,
                    monitor_hotkey="Ctrl+Alt+M",
                    monitor_hotkey_enabled=True,
                    monitor_ocr_concurrency=3,
                    audio_hotkey="Ctrl+Alt+A",
                    audio_hotkey_enabled=True,
                    audio_voice_relay_enabled=True,
                    audio_relay_output_device_id=12,
                    audio_relay_voice_name="Microsoft Test Voice",
                    audio_relay_rate=2,
                    audio_relay_volume=85,
                    audio_relay_queue_limit=3,
                )
                save_settings(original)
                loaded = load_settings()

        self.assertEqual(loaded.target_language, "ja")
        self.assertEqual(loaded.overlay_font_size, 18)
        self.assertEqual(loaded.overlay_scroll_speed, 4)
        self.assertEqual(loaded.translation_provider, "qwen_mt")
        self.assertEqual(loaded.translation_qwen_api_key, "translation-key")
        self.assertEqual(loaded.source_language, "ja")
        self.assertEqual(loaded.dashscope_api_key, "audio-key")
        self.assertEqual(loaded.audio_translation_model, "custom")
        self.assertEqual(
            loaded.audio_custom_translation_model_id,
            "qwen3.5-custom-realtime",
        )
        self.assertFalse(loaded.hotkey_enabled)
        self.assertEqual(loaded.monitor_hotkey, "Ctrl+Alt+M")
        self.assertTrue(loaded.monitor_hotkey_enabled)
        self.assertEqual(loaded.monitor_ocr_concurrency, 3)
        self.assertEqual(loaded.audio_hotkey, "Ctrl+Alt+A")
        self.assertTrue(loaded.audio_hotkey_enabled)
        self.assertTrue(loaded.audio_voice_relay_enabled)
        self.assertEqual(loaded.audio_relay_output_device_id, 12)
        self.assertEqual(loaded.audio_relay_voice_name, "Microsoft Test Voice")
        self.assertEqual(loaded.audio_relay_rate, 2)
        self.assertEqual(loaded.audio_relay_volume, 85)
        self.assertEqual(loaded.audio_relay_queue_limit, 3)

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

    def test_legacy_arbitrary_audio_model_is_migrated_to_custom(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"APPDATA": directory}):
                path = os.path.join(directory, "ScreenTranslator")
                os.makedirs(path)
                with open(
                    os.path.join(path, "settings.json"), "w", encoding="utf-8"
                ) as handle:
                    handle.write(
                        '{"audio_translation_model":"vendor-live-model"}'
                    )

                loaded = load_settings()

        self.assertEqual(loaded.audio_translation_model, "custom")
        self.assertEqual(
            loaded.audio_custom_translation_model_id, "vendor-live-model"
        )
