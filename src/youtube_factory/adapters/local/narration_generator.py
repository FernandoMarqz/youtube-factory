"""Deterministic PCM/WAV narration adapter for Phase 3."""

import wave
from hashlib import sha256
from io import BytesIO

from youtube_factory.application.exceptions import NarrationGenerationError
from youtube_factory.domain.models import Narration, Script
from youtube_factory.ports.narration import GeneratedNarration

_SAMPLE_RATE_HZ = 16_000
_DURATION_SECONDS = 36.72


class LocalNarrationGenerator:
    """Produces a deterministic silent WAV for any valid script without a TTS dependency."""

    identifier = "local-wav-narration-v1"

    def generate(self, script: Script) -> GeneratedNarration:
        """Create deterministic PCM/WAV bytes for the complete final script narration."""
        frame_count = int(_SAMPLE_RATE_HZ * _DURATION_SECONDS)
        try:
            buffer = BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(_SAMPLE_RATE_HZ)
                wav_file.writeframes(b"\x00\x00" * frame_count)
        except wave.Error as error:
            raise NarrationGenerationError(
                "could not generate deterministic WAV narration"
            ) from error
        narration = Narration(
            topic_id=script.topic_id,
            file_path="narration.wav",
            duration_seconds=_DURATION_SECONDS,
            provider="local",
            voice="synthetic-silence",
            audio_format="wav",
            sample_rate_hz=_SAMPLE_RATE_HZ,
            narration_text=script.full_narration,
            script_sha256=sha256(script.full_narration.encode("utf-8")).hexdigest(),
            input_character_count=len(script.full_narration),
        )
        return GeneratedNarration(narration=narration, audio_bytes=buffer.getvalue())
