"""Provider-neutral word timing from a persisted narration WAV."""

from typing import Protocol

from youtube_factory.domain.models import Narration, WordAlignment


class CaptionAlignmentProvider(Protocol):
    provider: str
    model: str | None
    identifier: str

    def align(self, narration: Narration, audio_bytes: bytes, language: str) -> WordAlignment:
        """Timestamp canonical narration words against the actual audio."""
