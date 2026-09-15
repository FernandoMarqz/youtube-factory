"""Provider-independent inspection of a persisted WAV artifact."""

from youtube_factory.application.exceptions import InvalidAudioArtifactError
from youtube_factory.application.services.wav import InvalidWavError, inspect_pcm_wav
from youtube_factory.domain.models import Narration


def validate_wav_narration(narration: Narration, audio_bytes: bytes) -> None:
    """Confirm that WAV bytes are readable and match the reported narration duration."""
    if narration.audio_format != "wav":
        raise InvalidAudioArtifactError("narration must use WAV audio")
    try:
        wav_info = inspect_pcm_wav(audio_bytes)
    except InvalidWavError as error:
        raise InvalidAudioArtifactError(
            "generated narration is not a readable WAV artifact"
        ) from error
    if wav_info.channels != 1 or wav_info.sample_width_bytes != 2:
        raise InvalidAudioArtifactError("narration WAV must be mono 16-bit PCM")
    if wav_info.sample_rate_hz != narration.sample_rate_hz:
        raise InvalidAudioArtifactError("WAV sample rate does not match narration metadata")
    actual_duration = wav_info.duration_seconds
    if abs(actual_duration - narration.duration_seconds) > 0.001:
        raise InvalidAudioArtifactError("WAV duration does not match narration metadata")
