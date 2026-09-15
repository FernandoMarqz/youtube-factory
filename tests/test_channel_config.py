"""Tests for typed, immutable channel configuration loading."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from youtube_factory.application.config import load_channel_config
from youtube_factory.application.exceptions import ChannelConfigurationError, ChannelNotFoundError


def test_engineering_channel_loads_with_expected_typed_values() -> None:
    config = load_channel_config("engineering-es")

    assert config.id == "engineering-es"
    assert config.language == "es-ES"
    assert config.content.target_duration_seconds == 35
    assert config.narration.provider == "openai"
    assert config.narration.model == "gpt-4o-mini-tts"
    assert config.visuals.aspect_ratio == "9:16"
    assert config.visuals.model == "gpt-image-2"
    assert config.publishing.enabled is False
    with pytest.raises(ValidationError):
        config.language = "en-US"


def write_channel(tmp_path: Path, content: str, channel_id: str = "test-channel") -> Path:
    """Write one isolated YAML channel fixture and return its directory."""
    channels_directory = tmp_path / "channels"
    channels_directory.mkdir()
    (channels_directory / f"{channel_id}.yaml").write_text(content, encoding="utf-8")
    return channels_directory


def valid_channel_yaml(overrides: str = "") -> str:
    """Return a valid channel YAML fixture with optional top-level replacement content."""
    if overrides:
        return overrides
    return """
id: test-channel
language: es-ES
content:
  niche: engineering_curiosities
  target_duration_seconds: 35
  min_duration_seconds: 25
  max_duration_seconds: 45
narration:
  provider: openai
  model: gpt-4o-mini-tts
  voice: cedar
  instructions: Clear delivery.
visuals:
  provider: local-placeholder
  aspect_ratio: "9:16"
  width: 1024
  height: 1536
  style: educational
publishing:
  enabled: false
"""


def test_missing_channel_file_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(ChannelNotFoundError, match="not found"):
        load_channel_config("missing", tmp_path)


def test_malformed_yaml_fails_clearly(tmp_path: Path) -> None:
    channels_directory = write_channel(tmp_path, "id: [unterminated", "broken")

    with pytest.raises(ChannelConfigurationError, match="could not load"):
        load_channel_config("broken", channels_directory)


@pytest.mark.parametrize(
    "yaml_content",
    [
        valid_channel_yaml().replace("id: test-channel", "id: ''"),
        valid_channel_yaml().replace("min_duration_seconds: 25", "min_duration_seconds: 40"),
        valid_channel_yaml().replace("provider: openai", "provider: unsupported", 1),
        valid_channel_yaml().replace("  model: gpt-4o-mini-tts\n", ""),
        valid_channel_yaml().replace("  voice: cedar\n", ""),
        valid_channel_yaml().replace("width: 1024", "width: 0"),
        valid_channel_yaml().replace("provider: local-placeholder", "provider: unsupported", 1),
    ],
)
def test_invalid_channel_schema_fails_clearly(tmp_path: Path, yaml_content: str) -> None:
    channels_directory = write_channel(tmp_path, yaml_content)

    with pytest.raises(ChannelConfigurationError, match="invalid channel"):
        load_channel_config("test-channel", channels_directory)


def test_filename_and_channel_id_must_match(tmp_path: Path) -> None:
    channels_directory = write_channel(
        tmp_path, valid_channel_yaml().replace("test-channel", "other")
    )

    with pytest.raises(ChannelConfigurationError, match="does not match"):
        load_channel_config("test-channel", channels_directory)


def test_loader_rejects_an_unsafe_channel_id() -> None:
    with pytest.raises(ChannelConfigurationError, match="lowercase"):
        load_channel_config("../engineering-es")


def test_openai_visual_provider_requires_a_model(tmp_path: Path) -> None:
    yaml_content = valid_channel_yaml().replace(
        "provider: local-placeholder", "provider: openai", 1
    )
    channels_directory = write_channel(tmp_path, yaml_content)

    with pytest.raises(ChannelConfigurationError, match="invalid channel"):
        load_channel_config("test-channel", channels_directory)


def test_openai_visual_provider_with_model_is_valid(tmp_path: Path) -> None:
    yaml_content = valid_channel_yaml().replace(
        "provider: local-placeholder",
        "provider: openai\n  model: gpt-image-2",
        1,
    )
    channels_directory = write_channel(tmp_path, yaml_content)

    config = load_channel_config("test-channel", channels_directory)

    assert config.visuals.provider == "openai"
    assert config.visuals.model == "gpt-image-2"
