"""Persistent application configuration."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


APP_NAME = "ScreenTranslator"


@dataclass
class AppSettings:
    translation_url: str = "https://api.mymemory.translated.net/get"
    translation_api_key: str = ""
    tesseract_path: str = ""
    source_language: str = "en"
    target_language: str = "zh-CN"
    hotkey: str = "Ctrl+Shift+T"
    overlay_x: int = -1
    overlay_y: int = -1
    overlay_opacity: int = 82
    overlay_text_opacity: int = 100
    overlay_font_size: int = 14
    overlay_mask_opacity: int = 45
    dashscope_api_key: str = ""
    audio_source_mode: str = "global"
    audio_device_id: int = -1
    audio_process_id: int = 0
    audio_process_name: str = ""
    audio_include_children: bool = True
    audio_source_language: str = "auto"
    audio_target_language: str = "zh"
    audio_sample_rate: int = 16000
    audio_vad_mode: int = 2
    audio_vad_start_ms: int = 60
    audio_vad_pre_roll_ms: int = 240
    audio_vad_post_roll_ms: int = 500
    audio_history_limit: int = 10
    audio_background_opacity: int = 82
    audio_text_opacity: int = 100
    audio_mask_opacity: int = 45
    audio_window_x: int = -1
    audio_window_y: int = -1


def settings_path() -> Path:
    app_data = os.environ.get("APPDATA") or str(Path.home())
    folder = Path(app_data) / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "settings.json"


def load_settings() -> AppSettings:
    path = settings_path()
    if not path.exists():
        return AppSettings()
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        allowed = asdict(AppSettings())
        settings = AppSettings(**{key: values[key] for key in allowed if key in values})
        if settings.translation_url == "https://libretranslate.com/translate":
            settings.translation_url = AppSettings().translation_url
            settings.target_language = AppSettings().target_language
        return settings
    except (OSError, ValueError, TypeError):
        return AppSettings()


def save_settings(settings: AppSettings) -> None:
    settings_path().write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8"
    )
