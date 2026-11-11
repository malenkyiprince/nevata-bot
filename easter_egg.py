"""Общий серверный триггер для текста, прочитанной ссылки и OCR фотографии."""
import re
import unicodedata


def is_nazar(text):
    if not isinstance(text, str):
        return False
    words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold())
    name = any(re.fullmatch(r"назар(?:а|ом|у)?", word) for word in words)
    surname = any(re.fullmatch(r"радков(?:ськ(?:ий|ого|ому|им)|ск(?:ий|ого|ому|им))", word) for word in words)
    return name and surname


def secret_result(text):
    text = text.strip()
    match = re.search(r"назар|радков", text, re.IGNORECASE)
    start = max(0, match.start() - 300) if match and len(text) > 1800 else 0
    context = ("…" if start else "") + text[start:start + 1800]
    return {"version": 2, "easterEgg": "nazar", "easterEggText": context,
        "label": "Секретний розділ ✦", "score": None, "limited": False, "segments": [], "sources": []}
