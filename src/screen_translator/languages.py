"""Shared language options for translation providers and OCR."""

from __future__ import annotations

import re

# Qwen-MT accepts the English language name in translation_options.  Keep the
# app-facing code stable so the settings file remains readable and upgradeable.
QWEN_LANGUAGE_OPTIONS: tuple[tuple[str, str, str], ...] = (
    ("auto", "自动检测", "auto"),
    ("en", "英语", "English"),
    ("zh-CN", "简体中文", "Chinese"),
    ("zh-TW", "繁体中文", "Traditional Chinese"),
    ("ja", "日语", "Japanese"),
    ("ko", "韩语", "Korean"),
    ("es", "西班牙语", "Spanish"),
    ("fr", "法语", "French"),
    ("de", "德语", "German"),
    ("pt", "葡萄牙语", "Portuguese"),
    ("it", "意大利语", "Italian"),
    ("ru", "俄语", "Russian"),
    ("th", "泰语", "Thai"),
    ("vi", "越南语", "Vietnamese"),
    ("id", "印度尼西亚语", "Indonesian"),
    ("ms", "马来语", "Malay"),
    ("ar", "阿拉伯语", "Arabic"),
    ("hi", "印地语", "Hindi"),
    ("he", "希伯来语", "Hebrew"),
    ("my", "缅甸语", "Burmese"),
    ("ta", "泰米尔语", "Tamil"),
    ("ur", "乌尔都语", "Urdu"),
    ("bn", "孟加拉语", "Bengali"),
    ("pl", "波兰语", "Polish"),
    ("nl", "荷兰语", "Dutch"),
    ("ro", "罗马尼亚语", "Romanian"),
    ("tr", "土耳其语", "Turkish"),
    ("km", "高棉语", "Khmer"),
    ("lo", "老挝语", "Lao"),
    ("yue", "粤语", "Cantonese"),
    ("cs", "捷克语", "Czech"),
    ("el", "希腊语", "Greek"),
    ("sv", "瑞典语", "Swedish"),
    ("hu", "匈牙利语", "Hungarian"),
    ("da", "丹麦语", "Danish"),
    ("fi", "芬兰语", "Finnish"),
    ("uk", "乌克兰语", "Ukrainian"),
    ("bg", "保加利亚语", "Bulgarian"),
    ("sr", "塞尔维亚语", "Serbian"),
    ("te", "泰卢固语", "Telugu"),
    ("af", "南非荷兰语", "Afrikaans"),
    ("hy", "亚美尼亚语", "Armenian"),
    ("as", "阿萨姆语", "Assamese"),
    ("ast", "阿斯图里亚斯语", "Asturian"),
    ("eu", "巴斯克语", "Basque"),
    ("be", "白俄罗斯语", "Belarusian"),
    ("bs", "波斯尼亚语", "Bosnian"),
    ("ca", "加泰罗尼亚语", "Catalan"),
    ("ceb", "宿务语", "Cebuano"),
    ("hr", "克罗地亚语", "Croatian"),
    ("arz", "埃及阿拉伯语", "Egyptian Arabic"),
    ("et", "爱沙尼亚语", "Estonian"),
    ("gl", "加利西亚语", "Galician"),
    ("ka", "格鲁吉亚语", "Georgian"),
    ("gu", "古吉拉特语", "Gujarati"),
    ("is", "冰岛语", "Icelandic"),
    ("jv", "爪哇语", "Javanese"),
    ("kn", "卡纳达语", "Kannada"),
    ("kk", "哈萨克语", "Kazakh"),
    ("lv", "拉脱维亚语", "Latvian"),
    ("lt", "立陶宛语", "Lithuanian"),
    ("lb", "卢森堡语", "Luxembourgish"),
    ("mk", "马其顿语", "Macedonian"),
    ("mai", "迈蒂利语", "Maithili"),
    ("mt", "马耳他语", "Maltese"),
    ("mr", "马拉地语", "Marathi"),
    ("acm", "美索不达米亚阿拉伯语", "Mesopotamian Arabic"),
    ("ary", "摩洛哥阿拉伯语", "Moroccan Arabic"),
    ("ars", "纳吉迪阿拉伯语", "Najdi Arabic"),
    ("ne", "尼泊尔语", "Nepali"),
    ("az", "北阿塞拜疆语", "North Azerbaijani"),
    ("apc", "北黎凡特阿拉伯语", "North Levantine Arabic"),
    ("uz", "北乌兹别克语", "Northern Uzbek"),
    ("nb", "书面挪威语", "Norwegian Bokmål"),
    ("nn", "新挪威语", "Norwegian Nynorsk"),
    ("oc", "奥克语", "Occitan"),
    ("or", "奥里亚语", "Odia"),
    ("pag", "邦阿西楠语", "Pangasinan"),
    ("scn", "西西里语", "Sicilian"),
    ("sd", "信德语", "Sindhi"),
    ("si", "僧伽罗语", "Sinhala"),
    ("sk", "斯洛伐克语", "Slovak"),
    ("sl", "斯洛文尼亚语", "Slovenian"),
    ("ajp", "南黎凡特阿拉伯语", "South Levantine Arabic"),
    ("sw", "斯瓦希里语", "Swahili"),
    ("tl", "菲律宾语", "Tagalog"),
    ("acq", "塔伊兹-亚丁阿拉伯语", "Ta’izzi-Adeni Arabic"),
    ("sq", "托斯克阿尔巴尼亚语", "Tosk Albanian"),
    ("aeb", "突尼斯阿拉伯语", "Tunisian Arabic"),
    ("vec", "威尼斯语", "Venetian"),
    ("war", "瓦瑞语", "Waray"),
    ("cy", "威尔士语", "Welsh"),
    ("fa", "波斯语", "Western Persian"),
)

# qwen-mt-lite has a smaller, documented language set than the other models.
QWEN_LITE_LANGUAGE_CODES = frozenset(
    {
        "en", "zh-CN", "zh-TW", "ru", "ja", "ko", "es", "fr", "pt", "de",
        "it", "th", "vi", "id", "ms", "ar", "hi", "he", "ur", "bn", "pl",
        "nl", "tr", "km", "cs", "sv", "hu", "da", "fi", "tl", "fa",
    }
)


def qwen_language_name(value: str) -> str:
    """Return the English language name required by Qwen-MT."""
    normalized = normalize_qwen_code(value)
    return dict((code, name) for code, _label, name in QWEN_LANGUAGE_OPTIONS).get(
        normalized, normalized
    )


def normalize_qwen_code(value: str) -> str:
    """Normalize language codes used by older settings files."""
    aliases = {
        "zh": "zh-CN",
        "zh_tw": "zh-TW",
        "en-US": "en",
        "ja-JP": "ja",
        "ko-KR": "ko",
    }
    normalized = value.strip()
    return aliases.get(normalized, normalized)


def qwen_language_options(model: str, include_auto: bool = False) -> tuple[tuple[str, str, str], ...]:
    """Return language options supported by the selected Qwen-MT model."""
    options = QWEN_LANGUAGE_OPTIONS
    if model == "qwen-mt-lite":
        options = tuple(
            option
            for option in options
            if option[0] == "auto" or option[0] in QWEN_LITE_LANGUAGE_CODES
        )
    if include_auto:
        return options
    return tuple(option for option in options if option[0] != "auto")


def language_display_label(value: str) -> str:
    """Return the localized label used by the main-window language indicator."""
    normalized = normalize_qwen_code(value)
    if normalized == "auto":
        return "自动检测"
    if normalized == "unknown":
        return "未识别"
    for code, label, _name in QWEN_LANGUAGE_OPTIONS:
        if code == normalized:
            return label
    return normalized


_LATIN_LANGUAGE_MARKERS: dict[str, frozenset[str]] = {
    "en": frozenset("the and is are this that with from you for have not".split()),
    "fr": frozenset("le la les des une un est sont avec dans pour que pas".split()),
    "de": frozenset("der die das ein eine ist sind mit nicht und für von".split()),
    "es": frozenset("el la los las una un es son con para que por del".split()),
    "it": frozenset("il lo la gli le una un è sono con per che non".split()),
    "pt": frozenset("o a os as uma um é são com para que não dos das".split()),
    "nl": frozenset("de het een is zijn met voor van niet dat en".split()),
    "tr": frozenset("bir ve bu için ile değil olan olanlar".split()),
    "vi": frozenset("một và là các cho với không trong của".split()),
    "id": frozenset("yang dan ini adalah untuk dengan tidak dari".split()),
    "pl": frozenset("jest są nie dla z tym że oraz".split()),
    "ro": frozenset("este sunt pentru cu și din nu care".split()),
}

_COMMON_LANGUAGE_WORDS: dict[str, str] = {
    "hello": "en",
    "hi": "en",
    "thanks": "en",
    "hola": "es",
    "gracias": "es",
    "adiós": "es",
    "adios": "es",
    "bonjour": "fr",
    "salut": "fr",
    "merci": "fr",
    "hallo": "de",
    "danke": "de",
    "ciao": "it",
    "grazie": "it",
    "olá": "pt",
    "ola": "pt",
    "obrigado": "pt",
    "obrigada": "pt",
    "привет": "ru",
    "спасибо": "ru",
}


def detect_language(text: str) -> str:
    """Make a lightweight local language estimate for auto-detect indicators.

    OCR and the audio streaming API expose the recognized text but do not
    consistently return a source-language field. Script detection handles
    non-Latin languages; common function words and diacritics provide a
    conservative estimate for Latin-script languages.
    """
    if not text or not text.strip():
        return "unknown"

    def count_in_ranges(ranges: tuple[tuple[int, int], ...]) -> int:
        return sum(
            1
            for char in text
            if any(start <= ord(char) <= end for start, end in ranges)
        )

    if count_in_ranges(((0xAC00, 0xD7AF),)):
        return "ko"
    if count_in_ranges(((0x3040, 0x30FF),)):
        return "ja"
    if count_in_ranges(((0x4E00, 0x9FFF),)):
        return "zh-CN"
    script_languages = (
        ("ar", ((0x0600, 0x06FF),)),
        ("th", ((0x0E00, 0x0E7F),)),
        ("hi", ((0x0900, 0x097F),)),
        ("he", ((0x0590, 0x05FF),)),
        ("el", ((0x0370, 0x03FF),)),
        ("ka", ((0x10A0, 0x10FF),)),
        ("hy", ((0x0530, 0x058F),)),
        ("bn", ((0x0980, 0x09FF),)),
        ("ta", ((0x0B80, 0x0BFF),)),
        ("te", ((0x0C00, 0x0C7F),)),
        ("gu", ((0x0A80, 0x0AFF),)),
        ("kn", ((0x0C80, 0x0CFF),)),
    )
    for code, ranges in script_languages:
        if count_in_ranges(ranges):
            return code
    if count_in_ranges(((0x0400, 0x04FF),)):
        return "ru"

    tokens = re.findall(r"[^\W\d_]+", text.lower(), flags=re.UNICODE)
    if not tokens:
        return "unknown"
    for token in tokens:
        detected = _COMMON_LANGUAGE_WORDS.get(token)
        if detected:
            return detected
    scores = {
        code: sum(token in markers for token in tokens)
        for code, markers in _LATIN_LANGUAGE_MARKERS.items()
    }
    accents = {
        "fr": "àâçéèêëîïôùûüÿœ",
        "de": "äöüß",
        "es": "áéíóúüñ¿¡",
        "pt": "ãõáâçéêíóôú",
        "it": "àèéìíîòóù",
        "tr": "çğıöşü",
        "vi": "ăâêôơưđ",
        "pl": "ąćęłńóśźż",
        "ro": "ăâîșț",
    }
    lowered = text.lower()
    for code, characters in accents.items():
        scores[code] += sum(lowered.count(character) for character in characters)
    best_code, best_score = max(scores.items(), key=lambda item: item[1])
    return best_code if best_score > 0 else "en"


# The main window's source-language choice also drives OCR. These codes map
# the translation language values to Tesseract's traineddata names.
TESSERACT_LANGUAGE_BY_SOURCE = {
    "en": "eng",
    "zh-CN": "chi_sim",
    "zh-TW": "chi_tra",
    "ja": "jpn",
    "ko": "kor",
    "fr": "fra",
    "de": "deu",
    "es": "spa",
    "ru": "rus",
    "it": "ita",
    "pt": "por",
    "vi": "vie",
    "th": "tha",
    "ar": "ara",
    "id": "ind",
    "ms": "msa",
    "hi": "hin",
    "nl": "nld",
    "pl": "pol",
    "tr": "tur",
}
AUTO_OCR_LANGUAGE = "+".join(TESSERACT_LANGUAGE_BY_SOURCE.values())


def tesseract_language_for_source(value: str) -> str:
    """Return the bundled Tesseract language bundle for a source language."""
    normalized = normalize_qwen_code(value)
    if normalized == "auto":
        return AUTO_OCR_LANGUAGE
    return TESSERACT_LANGUAGE_BY_SOURCE.get(normalized, "eng")
