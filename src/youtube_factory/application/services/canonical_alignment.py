"""Reconcile acoustic transcription timing with immutable canonical narration text."""

import re
import unicodedata
from difflib import SequenceMatcher

from youtube_factory.application.exceptions import CaptionAlignmentError
from youtube_factory.domain.models import AlignedWord

MIN_MATCH_RATIO = 0.9


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in decomposed if character.isalnum())


def reconcile_words(canonical: str, recognized: list[AlignedWord]) -> list[AlignedWord]:
    """Keep canonical tokens, borrowing only the recognized words' acoustic intervals."""
    tokens = re.findall(r"\S+", canonical)
    if not tokens or not recognized:
        raise CaptionAlignmentError("canonical narration or transcription is empty")
    canonical_chars: list[str] = []
    canonical_owner: list[int] = []
    for index, token in enumerate(tokens):
        for character in _normalized(token):
            canonical_chars.append(character)
            canonical_owner.append(index)
    provider_chars: list[str] = []
    provider_owner: list[tuple[int, int, int]] = []
    for index, word in enumerate(recognized):
        normalized = _normalized(word.text)
        for offset, character in enumerate(normalized):
            provider_chars.append(character)
            provider_owner.append((index, offset, len(normalized)))
    if not canonical_chars or not provider_chars:
        raise CaptionAlignmentError("canonical narration or transcription has no comparable words")
    matches: list[list[float]] = [[] for _ in tokens]
    for block in SequenceMatcher(
        None, canonical_chars, provider_chars, autojunk=False
    ).get_matching_blocks():
        for offset in range(block.size):
            canonical_index = canonical_owner[block.a + offset]
            provider_index, provider_offset, provider_length = provider_owner[block.b + offset]
            word = recognized[provider_index]
            fraction = provider_offset / provider_length
            next_fraction = (provider_offset + 1) / provider_length
            duration = word.end_seconds - word.start_seconds
            matches[canonical_index].extend(
                (
                    word.start_seconds + duration * fraction,
                    word.start_seconds + duration * next_fraction,
                )
            )
    for index, values in enumerate(matches):
        if len(values) / 2 < 0.7 * len(_normalized(tokens[index])):
            matches[index] = []
    matched = sum(bool(values) for values in matches)
    ratio = matched / len(tokens)
    if ratio < MIN_MATCH_RATIO:
        raise CaptionAlignmentError(
            f"canonical alignment matched {matched}/{len(tokens)} tokens; "
            f"minimum required ratio: {MIN_MATCH_RATIO:.0%}"
        )
    intervals: list[tuple[float, float] | None] = [
        (min(values), max(values)) if values else None for values in matches
    ]
    index = 0
    while index < len(intervals):
        if intervals[index] is not None:
            index += 1
            continue
        run_start = index
        while index < len(intervals) and intervals[index] is None:
            index += 1
        previous = intervals[run_start - 1] if run_start else None
        following = intervals[index] if index < len(intervals) else None
        left = previous[1] if previous else recognized[0].start_seconds
        right = following[0] if following else recognized[-1].end_seconds
        count = index - run_start
        if right - left <= 0.01 * count:
            raise CaptionAlignmentError(
                f"cannot timestamp unmatched canonical token {run_start + 1}"
            )
        for offset in range(count):
            intervals[run_start + offset] = (
                left + (right - left) * offset / count,
                left + (right - left) * (offset + 1) / count,
            )
    output = [
        AlignedWord(text=token, start_seconds=interval[0], end_seconds=interval[1])
        for token, interval in zip(tokens, intervals, strict=True)
        if interval is not None
    ]
    return output
