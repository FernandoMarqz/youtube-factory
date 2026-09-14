"""Narration-generation provider boundary."""

from dataclasses import dataclass
from typing import Protocol

from youtube_factory.domain.models import Narration, Script


@dataclass(frozen=True, slots=True)
class GeneratedNarration:
    """Validated narration metadata plus the binary audio artifact to persist."""

    narration: Narration
    audio_bytes: bytes

    def __post_init__(self) -> None:
        """Reject empty binary audio before it reaches infrastructure."""
        if not self.audio_bytes:
            raise ValueError("generated narration audio must not be empty")


class NarrationGenerator(Protocol):
    """Produces one complete narration track for a script."""

    identifier: str

    def generate(self, script: Script) -> GeneratedNarration:
        """Generate narration metadata and a binary audio artifact."""
