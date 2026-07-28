"""Persistent application configuration."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


APP_NAME = "ScreenTranslator"


@dataclass
class AppSettings:
    # Screenshot/continuous-monitor translation settings.  These are kept
    # separate from the audio DashScope credentials below on purpose.
    translation_provider: str = "mymemory"
    translation_url: str = "https://api.mymemory.translated.net/get"
    translation_api_key: str = ""
    translation_qwen_api_key: str = ""
    translation_qwen_model: str = "qwen-mt-flash"
    tesseract_path: str = ""
    source_language: str = "en"
    target_language: str = "zh-CN"
    hotkey: str = "Ctrl+Shift+T"
    hotkey_enabled: bool = False
    monitor_hotkey: str = "Ctrl+Shift+M"
    monitor_hotkey_enabled: bool = False
    monitor_ocr_concurrency: int = 1
    audio_hotkey: str = "Ctrl+Shift+A"
    audio_hotkey_enabled: bool = False
    overlay_x: int = -1
    overlay_y: int = -1
    overlay_opacity: int = 82
    overlay_text_opacity: int = 100
    overlay_font_size: int = 14
    overlay_mask_opacity: int = 45
    overlay_scroll_speed: int = 1
    overlay_width: int = 520
    overlay_height: int = 220
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
    audio_history_text_opacity: int = 100
    audio_show_original: bool = True
    audio_font_scale: int = 100
    audio_mask_opacity: int = 45
    audio_window_x: int = -1
    audio_window_y: int = -1
    audio_window_width: int = 560
    audio_window_height: int = 430


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
        if not isinstance(values, dict):
            return AppSettings()

        defaults = AppSettings()
        allowed = asdict(defaults)
        valid_values = {}
        for key, default in allowed.items():
            if key not in values:
                continue
            value = values[key]
            # AppSettings intentionally contains only primitive fields.  Do
            # not let malformed JSON values reach Qt widgets or arithmetic
            # used by the workers during application startup.
            if isinstance(default, bool):
                is_valid = isinstance(value, bool)
            else:
                is_valid = isinstance(value, type(default))
            if is_valid:
                valid_values[key] = value
        settings = AppSettings(**valid_values)
        # Older settings files had no provider field. Preserve a custom URL
        # instead of silently treating it as MyMemory after upgrading.
        if "translation_provider" not in values:
            settings.translation_provider = (
                "mymemory"
                if "mymemory.translated.net" in settings.translation_url
                else "custom"
            )
        if settings.translation_provider not in {"mymemory", "qwen_mt", "custom"}:
            settings.translation_provider = "mymemory"
        if settings.translation_url == "https://libretranslate.com/translate":
            settings.translation_url = AppSettings().translation_url
            settings.target_language = AppSettings().target_language
        return settings
    except (OSError, ValueError, TypeError):
        return AppSettings()


def save_settings(settings: AppSettings) -> None:
    path = settings_path()
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_path.replace(path)
