import os
import tempfile
import unittest
from unittest.mock import patch

from screen_translator.config import AppSettings, load_settings, save_settings


class ConfigTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"APPDATA": directory}):
                original = AppSettings(target_language="ja", overlay_font_size=18)
                save_settings(original)
                loaded = load_settings()

        self.assertEqual(loaded.target_language, "ja")
        self.assertEqual(loaded.overlay_font_size, 18)

    def test_invalid_json_returns_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"APPDATA": directory}):
                path = os.path.join(directory, "ScreenTranslator")
                os.makedirs(path)
                with open(os.path.join(path, "settings.json"), "w", encoding="utf-8") as handle:
                    handle.write("not-json")
                self.assertEqual(load_settings(), AppSettings())

