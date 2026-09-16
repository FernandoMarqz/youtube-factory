"""OpenAI word-timestamp transcription behind the alignment port."""

from dataclasses import dataclass
from math import isfinite
from typing import Any

from youtube_factory.application.exceptions import CaptionAlignmentError
from youtube_factory.application.services.canonical_alignment import reconcile_words
from youtube_factory.domain.models import AlignedWord, Narration, WordAlignment


@dataclass(frozen=True, slots=True)
class OpenAICaptionAlignmentConfig:
    api_key: str
    model: str


@dataclass(slots=True)
class _ProviderWord:
    text: str
    start: float
    end: float


_MIN_REPAIRED_WORD_SECONDS = 0.005
_MAX_REPAIRED_WORD_SECONDS = 0.02


def _validated_words(raw_words: Any, narration_duration: float) -> list[AlignedWord]:
    """Repair only zero-length provider intervals using adjacent acoustic time."""
    tokens = [
        _ProviderWord(str(word.word), round(float(word.start), 3), round(float(word.end), 3))
        for word in raw_words
    ]
    if not tokens:
        raise ValueError("empty transcription words")
    if not any(token.end > token.start for token in tokens):
        raise ValueError("transcription has no positive-duration word timestamps")
    for index, token in enumerate(tokens):
        if (
            not token.text.strip()
            or not isfinite(token.start)
            or not isfinite(token.end)
            or token.start < 0
            or token.end < token.start
            or token.end > narration_duration + 0.1
        ):
            raise ValueError(f"invalid transcription interval at word {index + 1}")
        if index and (token.start < tokens[index - 1].start or token.end < tokens[index - 1].end):
            raise ValueError(f"non-monotonic transcription interval at word {index + 1}")

    index = 0
    while index < len(tokens):
        if tokens[index].end > tokens[index].start:
            index += 1
            continue
        first = index
        anchor = tokens[index].start
        while index < len(tokens) and tokens[index].start == anchor and tokens[index].end == anchor:
            index += 1
        count = index - first
        following = tokens[index] if index < len(tokens) else None
        previous = tokens[first - 1] if first else None
        gap = following.start - anchor if following else narration_duration - anchor
        if gap >= count * _MIN_REPAIRED_WORD_SECONDS:
            span = min(_MAX_REPAIRED_WORD_SECONDS, gap / count)
            start = anchor
        elif (
            following is not None
            and following.end - anchor >= (count + 1) * _MIN_REPAIRED_WORD_SECONDS
        ):
            span = min(_MAX_REPAIRED_WORD_SECONDS, (following.end - anchor) / (count + 1))
            start = anchor
            following.start = anchor + count * span
        elif (
            previous is not None
            and anchor - previous.start >= (count + 1) * _MIN_REPAIRED_WORD_SECONDS
        ):
            span = min(_MAX_REPAIRED_WORD_SECONDS, (anchor - previous.start) / (count + 1))
            start = anchor - count * span
            previous.end = start
        else:
            raise ValueError(f"cannot repair zero-length interval at word {first + 1}")
        for offset in range(count):
            tokens[first + offset].start = start + offset * span
            tokens[first + offset].end = start + (offset + 1) * span
    return [
        AlignedWord(text=token.text, start_seconds=token.start, end_seconds=token.end)
        for token in tokens
    ]


class OpenAICaptionAlignmentProvider:
    """Use documented verbose word timestamps; never use transcription as display text."""

    provider = "openai"
    identifier = "openai-caption-alignment-v1"
    model: str | None

    def __init__(self, config: OpenAICaptionAlignmentConfig, client: Any | None = None) -> None:
        self.model = config.model
        self._config = config
        if not config.api_key:
            raise CaptionAlignmentError("OPENAI_API_KEY is required for OpenAI caption alignment")
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise CaptionAlignmentError("OpenAI SDK is not installed") from error
            client = OpenAI(api_key=config.api_key)
        self._client = client

    def align(self, narration: Narration, audio_bytes: bytes, language: str) -> WordAlignment:
        if not audio_bytes:
            raise CaptionAlignmentError("narration WAV is empty")
        try:
            response = self._client.audio.transcriptions.create(
                file=("narration.wav", audio_bytes, "audio/wav"),
                model=self._config.model,
                language=language.split("-")[0],
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )
        except Exception as error:
            name = type(error).__name__
            if name == "AuthenticationError":
                detail = "OpenAI caption alignment authentication failed"
            elif name == "RateLimitError":
                detail = "OpenAI caption alignment rate limit reached"
            elif name in {"APIConnectionError", "APITimeoutError"}:
                detail = "OpenAI caption alignment service is unavailable"
            else:
                detail = f"OpenAI caption alignment request failed: {name}: {str(error)[:400]}"
            raise CaptionAlignmentError(detail) from error
        try:
            raw_words = response.words
            if not raw_words:
                raise ValueError("empty transcription words")
            recognized = _validated_words(raw_words, narration.duration_seconds)
            words = reconcile_words(narration.narration_text, recognized)
            return WordAlignment(
                topic_id=narration.topic_id,
                provider=self.provider,
                model=self.model,
                duration_seconds=narration.duration_seconds,
                words=words,
            )
        except CaptionAlignmentError:
            raise
        except (AttributeError, TypeError, ValueError) as error:
            raise CaptionAlignmentError(f"invalid OpenAI word timestamps: {error}") from error
