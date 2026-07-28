"""Translation service adapters and long-text request handling."""

from __future__ import annotations

import html
import time

import requests

from .config import AppSettings
from .languages import normalize_qwen_code, qwen_language_name


# MyMemory rejects requests above 500 characters. Leave headroom for API
# differences and future providers that apply a slightly smaller limit.
MAX_TRANSLATION_CHARS = 450
# Qwen-MT accepts a much larger token window. Keep a conservative character
# budget so OCR text stays in one request without approaching its 8K-token cap.
QWEN_MAX_TRANSLATION_CHARS = 4000
TRANSLATION_TIMEOUT_SECONDS = 20
TRANSLATION_MAX_RETRIES = 2
_RETRYABLE_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


class _RetryableTranslationError(RuntimeError):
    """Internal marker for a service response that is safe to retry."""


def _qwen_language(value: str) -> str:
    """Convert the app's language values to Qwen-MT language names."""
    return qwen_language_name(normalize_qwen_code(value))


def _response_value(value, key: str, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _translate_qwen_chunk(text: str, settings: AppSettings) -> str:
    """Translate one text chunk through Alibaba Cloud Qwen-MT."""
    api_key = settings.translation_qwen_api_key.strip()
    if not api_key:
        raise RuntimeError("请先在截图翻译设置中填写阿里云 Qwen-MT API Key。")
    try:
        import dashscope
    except ImportError as exc:  # pragma: no cover - dependency is in production extras
        raise RuntimeError("当前环境未安装 dashscope，请先安装项目依赖。") from exc

    response = dashscope.Generation.call(
        api_key=api_key,
        model=settings.translation_qwen_model or "qwen-mt-flash",
        messages=[{"role": "user", "content": text}],
        translation_options={
            "source_lang": _qwen_language(settings.source_language),
            "target_lang": _qwen_language(settings.target_language),
        },
    )
    status_code = _response_value(response, "status_code", 200)
    if status_code not in (None, 200):
        if status_code in _RETRYABLE_HTTP_STATUS_CODES:
            raise _RetryableTranslationError(
                f"Qwen-MT temporarily unavailable (HTTP {status_code})"
            )
        if status_code == 403:
            raise RuntimeError(
                "阿里云百炼 API 返回 403：免费额度可能已用尽，请充值后继续使用。"
            )
        code = _response_value(response, "code", "")
        message = _response_value(response, "message", "")
        detail = ": ".join(str(item) for item in (code, message) if item)
        suffix = f"：{detail}" if detail else ""
        raise RuntimeError(f"阿里云 Qwen-MT 请求失败（HTTP {status_code}）{suffix}")

    output = _response_value(response, "output", {})
    choices = _response_value(output, "choices", []) or []
    if not choices:
        raise RuntimeError("阿里云 Qwen-MT 没有返回翻译结果。")
    message = _response_value(choices[0], "message", {})
    translated = _response_value(message, "content", "")
    if not isinstance(translated, str) or not translated.strip():
        raise RuntimeError("阿里云 Qwen-MT 没有返回翻译结果。")
    return translated.strip()


def split_text_for_translation(
    text: str, max_chars: int = MAX_TRANSLATION_CHARS
) -> list[str]:
    """Split text into bounded, readable chunks without breaking words when possible."""
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    text_length = len(text)
    boundary_chars = set(" \t\r\n.,!?;:，。！？；：、)]}»")

    while text_length - start > max_chars:
        hard_end = start + max_chars
        cut = hard_end
        for position in range(hard_end - 1, start, -1):
            if text[position].isspace() or text[position] in boundary_chars:
                cut = position + 1
                break

        chunk = text[start:cut].strip()
        if chunk:
            chunks.append(chunk)
        start = cut
        while start < text_length and text[start].isspace():
            start += 1

    tail = text[start:].strip()
    if tail:
        chunks.append(tail)
    return chunks


def _translate_chunk(text: str, settings: AppSettings) -> str:
    if settings.translation_provider == "qwen_mt":
        return _translate_qwen_chunk(text, settings)

    if settings.translation_provider == "mymemory":
        target_language = settings.target_language
        if target_language == "zh":
            target_language = "zh-CN"
        response = requests.get(
            settings.translation_url,
            params={
                "q": text,
                "langpair": f"{settings.source_language}|{target_language}",
            },
            timeout=TRANSLATION_TIMEOUT_SECONDS,
        )
    else:  # custom HTTP translation endpoint kept for compatibility
        payload = {
            "q": text,
            "source": settings.source_language,
            "target": settings.target_language,
            "format": "text",
        }
        if settings.translation_api_key:
            payload["api_key"] = settings.translation_api_key
        response = requests.post(
            settings.translation_url,
            json=payload,
            timeout=TRANSLATION_TIMEOUT_SECONDS,
        )

    if not response.ok:
        try:
            error_data = response.json()
            error_message = error_data.get("error", "")
        except ValueError:
            error_message = response.text.strip()
        detail = f"：{error_message}" if error_message else ""
        error = f"翻译接口返回 HTTP {response.status_code}{detail}"
        if response.status_code in _RETRYABLE_HTTP_STATUS_CODES:
            raise _RetryableTranslationError(error)
        raise RuntimeError(error)

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


def translate_text(
    text: str,
    settings: AppSettings,
    max_chars: int | None = None,
) -> str:
    """Translate text, splitting oversized requests and preserving their order."""
    if max_chars is None:
        max_chars = (
            QWEN_MAX_TRANSLATION_CHARS
            if settings.translation_provider == "qwen_mt"
            else MAX_TRANSLATION_CHARS
        )
    chunks = split_text_for_translation(text, max_chars=max_chars)
    if not chunks:
        return ""

    translated_chunks: list[str] = []
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        for attempt in range(TRANSLATION_MAX_RETRIES + 1):
            try:
                translated_chunks.append(_translate_chunk(chunk, settings))
                break
            except (requests.RequestException, _RetryableTranslationError) as exc:
                if attempt >= TRANSLATION_MAX_RETRIES:
                    if total > 1:
                        raise RuntimeError(
                            f"第 {index}/{total} 段翻译失败：{exc}"
                        ) from exc
                    raise
                time.sleep(0.5 * (2**attempt))
            except Exception as exc:  # noqa: BLE001 - add segment context for the UI
                if total > 1:
                    raise RuntimeError(f"第 {index}/{total} 段翻译失败：{exc}") from exc
                raise

    # Chunks are deliberately trimmed at whitespace/punctuation boundaries.
    # Newlines make separate API results readable in the existing result pane.
    return "\n".join(translated_chunks)
