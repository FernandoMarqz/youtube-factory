"""Offline tests for the OpenAI narration adapter and configuration."""

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from youtube_factory.adapters.local import (
    LocalNarrationGenerator,
    LocalResearchProvider,
    LocalScriptGenerator,
)
from youtube_factory.adapters.openai import OpenAINarrationGenerator, OpenAITTSConfig
from youtube_factory.application.exceptions import NarrationGenerationError
from youtube_factory.cli.main import build_narration_generator, load_local_environment
from youtube_factory.domain.models import Script, Topic


class FakeSpeechResponse:
    """Minimal SDK binary response fake."""

    def __init__(self, audio_bytes: bytes) -> None:
        self._audio_bytes = audio_bytes

    def read(self) -> bytes:
        return self._audio_bytes


class FakeOpenAIClient:
    """Minimal fake restricted to the SDK speech boundary used by the adapter."""

    def __init__(self, response: FakeSpeechResponse | Exception) -> None:
        self.response = response
        self.requests: list[dict[str, str]] = []
        self.audio = SimpleNamespace(speech=SimpleNamespace(create=self.create))

    def create(self, **kwargs: str) -> FakeSpeechResponse:
        self.requests.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class AuthenticationError(Exception):
    """Fake SDK exception named like the official authentication failure."""


def reference_script() -> Script:
    """Build the reference script through the deterministic preceding stages."""
    topic = Topic(id=uuid4(), title="¿Por qué las tapas de alcantarilla son redondas?")
    research = LocalResearchProvider().research(topic)
    return LocalScriptGenerator().generate(topic, research)


def test_openai_config_requires_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(NarrationGenerationError, match="OPENAI_API_KEY"):
        OpenAITTSConfig.from_environment()


def test_openai_config_reads_optional_environment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_TTS_MODEL", "configured-model")
    monkeypatch.setenv("OPENAI_TTS_VOICE", "configured-voice")

    config = OpenAITTSConfig.from_environment()

    assert config.model == "configured-model"
    assert config.voice == "configured-voice"


def test_cli_wiring_selects_openai_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    generator = build_narration_generator("openai")

    assert isinstance(generator, OpenAINarrationGenerator)


def test_local_dotenv_values_are_loaded_without_overwriting_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "OPENAI_API_KEY=dotenv-key\nOPENAI_TTS_VOICE=dotenv-voice\n", encoding="utf-8"
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_TTS_VOICE", raising=False)
    monkeypatch.chdir(tmp_path)

    assert load_local_environment()
    config = OpenAITTSConfig.from_environment()

    assert config.api_key == "dotenv-key"
    assert config.voice == "dotenv-voice"


def test_existing_environment_values_override_local_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "OPENAI_API_KEY=dotenv-key\nOPENAI_TTS_VOICE=dotenv-voice\n", encoding="utf-8"
    )
    monkeypatch.setenv("OPENAI_API_KEY", "process-key")
    monkeypatch.setenv("OPENAI_TTS_VOICE", "process-voice")

    assert load_local_environment(dotenv_path)

    config = OpenAITTSConfig.from_environment()

    assert config.api_key == "process-key"
    assert config.voice == "process-voice"


def test_local_provider_does_not_load_or_require_openai_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert isinstance(build_narration_generator("local"), LocalNarrationGenerator)


def test_openai_adapter_sends_configured_request_and_measures_wav() -> None:
    script = reference_script()
    local_audio = LocalNarrationGenerator().generate(script).audio_bytes
    client = FakeOpenAIClient(FakeSpeechResponse(local_audio))
    config = OpenAITTSConfig(
        api_key="test-key",
        model="gpt-4o-mini-tts",
        voice="cedar",
        instructions="Instrucciones de prueba.",
    )

    generated = OpenAINarrationGenerator(config, client=client).generate(script)

    assert client.requests == [
        {
            "model": "gpt-4o-mini-tts",
            "voice": "cedar",
            "input": script.full_narration,
            "instructions": "Instrucciones de prueba.",
            "response_format": "wav",
        }
    ]
    assert generated.audio_bytes == local_audio
    assert generated.narration.provider == "openai"
    assert generated.narration.model == "gpt-4o-mini-tts"
    assert generated.narration.voice == "cedar"
    assert generated.narration.duration_seconds == 36.72
    assert generated.narration.narration_text == script.full_narration


def test_openai_adapter_maps_sdk_errors_to_application_errors() -> None:
    client = FakeOpenAIClient(AuthenticationError("secret must not be shown"))
    config = OpenAITTSConfig(api_key="test-key")

    with pytest.raises(NarrationGenerationError, match="authentication failed"):
        OpenAINarrationGenerator(config, client=client).generate(reference_script())


def test_openai_adapter_rejects_invalid_wav_response() -> None:
    client = FakeOpenAIClient(FakeSpeechResponse(b"not a WAV file"))

    with pytest.raises(NarrationGenerationError, match="invalid WAV"):
        OpenAINarrationGenerator(OpenAITTSConfig(api_key="test-key"), client=client).generate(
            reference_script()
        )
