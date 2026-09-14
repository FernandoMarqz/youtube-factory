"""OpenAI Text-to-Speech adapter isolated behind the narration port."""

import os
import wave
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Any

from youtube_factory.application.exceptions import NarrationGenerationError
from youtube_factory.domain.models import Narration, Script
from youtube_factory.ports.narration import GeneratedNarration

DEFAULT_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "cedar"
DEFAULT_INSTRUCTIONS = (
    "Habla en español neutro, con energía natural, articulación clara y ritmo ágil educativo. "
    "Evita un tono de locutor de radio."
)


@dataclass(frozen=True, slots=True)
class OpenAITTSConfig:
    """Configuration required by the OpenAI TTS adapter, sourced outside the domain."""

    api_key: str
    model: str = DEFAULT_MODEL
    voice: str = DEFAULT_VOICE
    instructions: str = DEFAULT_INSTRUCTIONS

    @classmethod
    def from_environment(cls) -> "OpenAITTSConfig":
        """Read OpenAI TTS configuration without logging or persisting the secret."""
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise NarrationGenerationError(
                "OPENAI_API_KEY is required when narration provider is openai"
            )
        return cls(
            api_key=api_key,
            model=os.environ.get("OPENAI_TTS_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            voice=os.environ.get("OPENAI_TTS_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE,
            instructions=(
                os.environ.get("OPENAI_TTS_INSTRUCTIONS", DEFAULT_INSTRUCTIONS).strip()
                or DEFAULT_INSTRUCTIONS
            ),
        )


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
        duration_seconds, sample_rate_hz = _measure_wav(audio_bytes)
        narration = Narration(
            topic_id=script.topic_id,
            file_path="narration.wav",
            duration_seconds=duration_seconds,
            provider=self.identifier,
            voice=self._config.voice,
            audio_format="wav",
            sample_rate_hz=sample_rate_hz,
            narration_text=script.full_narration,
            script_sha256=sha256(script.full_narration.encode("utf-8")).hexdigest(),
            model=self._config.model,
            input_character_count=len(script.full_narration),
        )
        return GeneratedNarration(narration=narration, audio_bytes=audio_bytes)


def _create_openai_client(api_key: str) -> Any:
    """Instantiate the official SDK only when OpenAI is selected at the composition root."""
    try:
        from openai import OpenAI
    except ImportError as error:
        raise NarrationGenerationError("OpenAI SDK is not installed") from error
    return OpenAI(api_key=api_key)


def _measure_wav(audio_bytes: bytes) -> tuple[float, int]:
    """Read duration and sample rate from a WAV response without provider-specific metadata."""
    try:
        with wave.open(BytesIO(audio_bytes), "rb") as wav_file:
            sample_rate_hz = wav_file.getframerate()
            duration_seconds = wav_file.getnframes() / sample_rate_hz
    except (EOFError, wave.Error, ZeroDivisionError) as error:
        raise NarrationGenerationError(
            "OpenAI returned an invalid WAV narration artifact"
        ) from error
    return duration_seconds, sample_rate_hz


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
