"""Offline tests for the OpenAI narration adapter and channel-based composition."""

import struct
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from youtube_factory.adapters.local import (
    LocalNarrationGenerator,
    LocalResearchProvider,
    LocalScenePlanner,
    LocalScriptGenerator,
)
from youtube_factory.adapters.openai import OpenAINarrationGenerator, OpenAITTSConfig
from youtube_factory.application.config import (
    ChannelConfig,
    get_openai_api_key,
    load_local_environment,
)
from youtube_factory.application.exceptions import NarrationGenerationError
from youtube_factory.application.services import SceneTimingReconciler
from youtube_factory.cli.main import build_narration_generator
from youtube_factory.domain.models import Script, Topic


def channel_config(provider: str = "openai") -> ChannelConfig:
    """Return a valid minimal channel configuration for composition tests."""
    narration: dict[str, str] = {"provider": provider}
    if provider == "openai":
        narration.update(
            model="channel-model", voice="channel-voice", instructions="Channel instructions."
        )
    return ChannelConfig.model_validate(
        {
            "id": "test-channel",
            "language": "es-ES",
            "content": {
                "niche": "test",
                "target_duration_seconds": 35,
                "min_duration_seconds": 25,
                "max_duration_seconds": 45,
            },
            "scene_planning": {
                "provider": "local",
                "model": "gpt-5.6-luna",
                "min_scenes": 6,
                "max_scenes": 9,
                "target_scene_duration_seconds": 4.5,
            },
            "narration": narration,
            "visuals": {
                "provider": "local-placeholder",
                "aspect_ratio": "9:16",
                "width": 1024,
                "height": 1536,
                "style": "test",
            },
            "publishing": {"enabled": False},
        }
    )


def streamed_pcm_wav(duration_seconds: float) -> bytes:
    """Build an OpenAI-like streamed WAV with unknown RIFF and data chunk sizes."""
    sample_rate_hz = 24_000
    frames = int(sample_rate_hz * duration_seconds)
    pcm_payload = b"\x00\x00" * frames
    fmt_chunk = struct.pack(
        "<4sIHHIIHH", b"fmt ", 16, 1, 1, sample_rate_hz, sample_rate_hz * 2, 2, 16
    )
    data_chunk = b"data" + struct.pack("<I", 0xFFFFFFFF) + pcm_payload
    return b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVE" + fmt_chunk + data_chunk


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


def test_openai_composition_requires_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(NarrationGenerationError, match="OPENAI_API_KEY"):
        build_narration_generator(channel_config())


def test_local_dotenv_values_are_loaded_without_overwriting_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("OPENAI_API_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    assert load_local_environment()
    assert get_openai_api_key() == "dotenv-key"


def test_existing_environment_values_override_local_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENAI_API_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "process-key")

    assert load_local_environment(dotenv_path)
    assert get_openai_api_key() == "process-key"


def test_channel_composition_selects_openai_with_channel_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    generator = build_narration_generator(channel_config())

    assert isinstance(generator, OpenAINarrationGenerator)
    assert generator._config.model == "channel-model"
    assert generator._config.voice == "channel-voice"


def test_local_channel_provider_does_not_require_openai_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert isinstance(build_narration_generator(channel_config("local")), LocalNarrationGenerator)


def test_cli_provider_override_takes_precedence_over_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert isinstance(
        build_narration_generator(channel_config(), narration_provider_override="local"),
        LocalNarrationGenerator,
    )


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

    assert client.requests[0]["model"] == "gpt-4o-mini-tts"
    assert client.requests[0]["voice"] == "cedar"
    assert client.requests[0]["instructions"] == "Instrucciones de prueba."
    assert generated.narration.duration_seconds == 36.72


def test_openai_adapter_normalizes_streamed_wav_and_reconciles_actual_duration() -> None:
    script = reference_script()
    client = FakeOpenAIClient(FakeSpeechResponse(streamed_pcm_wav(34.25)))
    config = OpenAITTSConfig("test-key", "model", "voice", "instructions")

    generated = OpenAINarrationGenerator(config, client=client).generate(script)
    timed_plan = SceneTimingReconciler().reconcile(
        LocalScenePlanner().plan(script), generated.narration
    )

    assert generated.narration.duration_seconds == 34.25
    assert timed_plan.scenes[-1].end_seconds == 34.25


def test_openai_adapter_maps_sdk_errors_to_application_errors() -> None:
    client = FakeOpenAIClient(AuthenticationError("secret must not be shown"))
    config = OpenAITTSConfig("test-key", "model", "voice", "instructions")

    with pytest.raises(NarrationGenerationError, match="authentication failed"):
        OpenAINarrationGenerator(config, client=client).generate(reference_script())
