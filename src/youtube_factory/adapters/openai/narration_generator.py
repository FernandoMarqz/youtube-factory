"""OpenAI Text-to-Speech adapter isolated behind the narration port."""

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from youtube_factory.application.exceptions import NarrationGenerationError
from youtube_factory.application.services.wav import InvalidWavError, normalize_pcm_wav
from youtube_factory.domain.models import Narration, Script
from youtube_factory.ports.narration import GeneratedNarration


@dataclass(frozen=True, slots=True)
class OpenAITTSConfig:
    """Explicit OpenAI settings assembled by the application composition root."""

    api_key: str
    model: str
    voice: str
    instructions: str


class OpenAINarrationGenerator:
    """Generates provider-neutral narration metadata from OpenAI WAV speech output."""

    identifier = "openai"

    def __init__(self, config: OpenAITTSConfig, client: Any | None = None) -> None:
        self._config = config
        self._client = client if client is not None else _create_openai_client(config.api_key)

    def generate(self, script: Script) -> GeneratedNarration:
        """Request WAV speech for the complete script and measure the returned media duration."""
        try:
            response = self._client.audio.speech.create(
                model=self._config.model,
                voice=self._config.voice,
                input=script.full_narration,
                instructions=self._config.instructions,
                response_format="wav",
            )
            audio_bytes = bytes(response.read())
        except Exception as error:
            raise NarrationGenerationError(_openai_error_message(error)) from error
        if not audio_bytes:
            raise NarrationGenerationError("OpenAI returned an empty narration audio artifact")
        try:
            normalized_audio_bytes, wav_info = normalize_pcm_wav(audio_bytes)
        except InvalidWavError as error:
            raise NarrationGenerationError(
                "OpenAI returned an invalid WAV narration artifact"
            ) from error
        narration = Narration(
            topic_id=script.topic_id,
            file_path="narration.wav",
            duration_seconds=wav_info.duration_seconds,
            provider=self.identifier,
            voice=self._config.voice,
            audio_format="wav",
            sample_rate_hz=wav_info.sample_rate_hz,
            narration_text=script.full_narration,
            script_sha256=sha256(script.full_narration.encode("utf-8")).hexdigest(),
            model=self._config.model,
            input_character_count=len(script.full_narration),
        )
        return GeneratedNarration(narration=narration, audio_bytes=normalized_audio_bytes)


def _create_openai_client(api_key: str) -> Any:
    """Instantiate the official SDK only when OpenAI is selected at the composition root."""
    try:
        from openai import OpenAI
    except ImportError as error:
        raise NarrationGenerationError("OpenAI SDK is not installed") from error
    return OpenAI(api_key=api_key)


def _openai_error_message(error: Exception) -> str:
    """Map SDK failures without exposing provider details or secrets."""
    error_name = type(error).__name__
    if error_name == "AuthenticationError":
        return "OpenAI authentication failed"
    if error_name == "RateLimitError":
        return "OpenAI rate limit reached"
    if error_name in {"APIConnectionError", "APITimeoutError"}:
        return "OpenAI narration service is unavailable"
    return "OpenAI narration request failed"
