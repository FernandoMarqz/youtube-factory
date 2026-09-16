"""Deterministic synthetic alignment for offline assembly and tests."""

import re

from youtube_factory.domain.models import AlignedWord, Narration, WordAlignment


class LocalCaptionAlignmentProvider:
    """Synthetic timing, deliberately not represented as acoustic alignment."""

    provider = "local-synthetic"
    model: str | None = None
    identifier = "local-synthetic-caption-alignment-v1"

    def align(self, narration: Narration, audio_bytes: bytes, language: str) -> WordAlignment:
        del audio_bytes, language
        tokens = re.findall(r"\S+", narration.narration_text)
        count = len(tokens)
        words = [
            AlignedWord(
                text=token,
                start_seconds=narration.duration_seconds * index / count,
                end_seconds=narration.duration_seconds * (index + 1) / count,
            )
            for index, token in enumerate(tokens)
        ]
        return WordAlignment(
            topic_id=narration.topic_id,
            provider=self.provider,
            model=self.model,
            duration_seconds=narration.duration_seconds,
            words=words,
        )
