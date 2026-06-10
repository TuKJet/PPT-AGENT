import re

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*：\x00-\x1f]')
COLLAPSED_SEPARATORS = re.compile(r"[\s_]+")


def safe_filename_part(value: object, max_length: int = 80, fallback: str = "untitled") -> str:
    text = str(value or "").strip()
    text = INVALID_FILENAME_CHARS.sub("_", text)
    text = COLLAPSED_SEPARATORS.sub("_", text)
    text = text.strip(" ._")
    if not text:
        text = fallback
    return text[:max_length].rstrip(" ._") or fallback


def slide_filename(index: int, title: object, extension: str, title_limit: int = 20) -> str:
    suffix = extension.lstrip(".")
    safe_title = safe_filename_part(title, max_length=title_limit, fallback="slide")
    return f"{index:02d}_{safe_title}.{suffix}"
