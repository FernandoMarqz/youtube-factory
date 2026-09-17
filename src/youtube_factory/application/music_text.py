"""Comparison-only normalization for deterministic music profile matching."""

import re
import unicodedata


def normalize_music_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(re.findall(r"\w+", text, flags=re.UNICODE))


def matches_music_phrase(normalized_text: str, phrase: str) -> bool:
    normalized_phrase = normalize_music_text(phrase.replace("_", " "))
    return bool(normalized_phrase and f" {normalized_phrase} " in f" {normalized_text} ")
