"""Translation service adapters."""

from __future__ import annotations

import html

import requests

from .config import AppSettings


def translate_text(text: str, settings: AppSettings) -> str:
    """Translate OCR text using the configured MyMemory-compatible API."""
    if "mymemory.translated.net" in settings.translation_url:
        target_language = settings.target_language
        if target_language == "zh":
            target_language = "zh-CN"
        response = requests.get(
            settings.translation_url,
            params={
                "q": text,
                "langpair": f"{settings.source_language}|{target_language}",
            },
            timeout=30,
        )
    else:
        payload = {
            "q": text,
            "source": settings.source_language,
            "target": settings.target_language,
            "format": "text",
        }
        if settings.translation_api_key:
            payload["api_key"] = settings.translation_api_key
        response = requests.post(settings.translation_url, json=payload, timeout=30)

    if not response.ok:
        try:
            error_data = response.json()
            error_message = error_data.get("error", "")
        except ValueError:
            error_message = response.text.strip()
        detail = f"：{error_message}" if error_message else ""
        raise RuntimeError(f"翻译接口返回 HTTP {response.status_code}{detail}")

    data = response.json()
    if "mymemory.translated.net" in settings.translation_url:
        translated = data.get("responseData", {}).get("translatedText", "")
        if data.get("responseStatus") not in (None, 200):
            raise RuntimeError(data.get("responseDetails", "MyMemory 翻译失败"))
        translated = html.unescape(translated).strip()
    else:
        translated = data.get("translatedText", "").strip()

    if not translated:
        raise RuntimeError("翻译接口没有返回翻译结果，请检查接口地址或文本长度。")
    return translated

