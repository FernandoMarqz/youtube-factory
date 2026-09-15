"""Deterministic spoken-duration estimation for generated Short scripts."""

import re

from youtube_factory.application.exceptions import ScriptValidationError

_WORDS_PER_SECOND = 2.5


def estimate_spoken_duration_seconds(narration: str) -> float:
    """Estimate Spanish Short duration at a stable 150 spoken words per minute."""
    word_count = len(re.findall(r"\S+", narration.strip()))
    if word_count == 0:
        raise ScriptValidationError("generated narration is empty")
    return round(word_count / _WORDS_PER_SECOND, 2)
