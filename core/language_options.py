from typing import Optional, Dict

SUPPORTED_LANGUAGES = {"zh", "en", "vi", "ja", "ko", "ru", "fr", "es"}

LANGUAGE_MAP: Dict[str, Optional[str]] = {
    # Vietnamese GUI Labels
    "Tự động nhận diện": None,
    "Tiếng Trung (中文)": "zh",
    "Tiếng Anh (English)": "en",
    "Tiếng Việt": "vi",
    "Tiếng Nhật (日本語)": "ja",
    "Tiếng Hàn (한국어)": "ko",
    "Tiếng Nga (Русский)": "ru",
    "Tiếng Pháp (Français)": "fr",
    "Tiếng Tây Ban Nha": "es",
    
    # English internal labels
    "auto": None,
    "chinese": "zh",
    "english": "en",
    "vietnamese": "vi",
    "japanese": "ja",
    "korean": "ko",
    "russian": "ru",
    "french": "fr",
    "spanish": "es",
}

def resolve_language_code(lang_str: Optional[str]) -> Optional[str]:
    """
    Resolve language code from label or English name.
    If lang_str is None, returns None.
    If invalid language code, raises ValueError.
    """
    if lang_str is None:
        return None
        
    cleaned = lang_str.strip()
    if not cleaned:
        return None
        
    # Check if direct match with supported codes
    if cleaned in SUPPORTED_LANGUAGES:
        return cleaned
        
    cleaned_lower = cleaned.lower()
    if cleaned_lower in SUPPORTED_LANGUAGES:
        return cleaned_lower
        
    # Check lower-cased version mapping
    lookup = {k.lower(): v for k, v in LANGUAGE_MAP.items()}
    if cleaned_lower in lookup:
        return lookup[cleaned_lower]
        
    # Fallback to direct mapping (in case of case-sensitive matching or exact strings)
    if cleaned in LANGUAGE_MAP:
        return LANGUAGE_MAP[cleaned]
        
    raise ValueError(
        f"Invalid language option '{lang_str}'. Supported options: {', '.join(sorted(SUPPORTED_LANGUAGES))}"
    )
