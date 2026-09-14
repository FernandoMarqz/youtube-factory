"""Provider-independent inspection of the WAV artifact used in the local milestone."""

import wave
from io import BytesIO

from youtube_factory.application.exceptions import InvalidAudioArtifactError
from youtube_factory.domain.models import Narration


def validate_wav_narration(narration: Narration, audio_bytes: bytes) -> None:
    """Confirm that WAV bytes are readable and match the reported narration duration."""
    if narration.audio_format != "wav":
        raise InvalidAudioArtifactError("narration must use WAV audio")
    try:
        with wave.open(BytesIO(audio_bytes), "rb") as wav_file:
            if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
                raise InvalidAudioArtifactError("narration WAV must be mono 16-bit PCM")
            if wav_file.getframerate() != narration.sample_rate_hz:
                raise InvalidAudioArtifactError("WAV sample rate does not match narration metadata")
            actual_duration = wav_file.getnframes() / wav_file.getframerate()
    except (EOFError, wave.Error) as error:
        raise InvalidAudioArtifactError(
            "generated narration is not a readable WAV artifact"
        ) from error
    if abs(actual_duration - narration.duration_seconds) > 0.001:
        raise InvalidAudioArtifactError("WAV duration does not match narration metadata")
