"""Load validated channel configuration from version-controlled YAML files."""

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from youtube_factory.application.config.models import ChannelConfig
from youtube_factory.application.exceptions import ChannelConfigurationError, ChannelNotFoundError

_CHANNEL_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DEFAULT_CHANNELS_DIRECTORY = Path("config/channels")


def load_channel_config(
    channel_id: str, channels_directory: Path = DEFAULT_CHANNELS_DIRECTORY
) -> ChannelConfig:
    """Read one channel YAML file and return its immutable validated configuration."""
    if not _CHANNEL_ID_PATTERN.fullmatch(channel_id):
        raise ChannelConfigurationError(
            "channel id must contain lowercase letters, numbers or hyphens"
        )
    config_path = channels_directory / f"{channel_id}.yaml"
    if not config_path.is_file():
        raise ChannelNotFoundError(f"channel configuration not found: {channel_id}")
    try:
        raw_config: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ChannelConfigurationError(
            f"could not load channel configuration: {channel_id}"
        ) from error
    try:
        config = ChannelConfig.model_validate(raw_config)
    except ValidationError as error:
        raise ChannelConfigurationError(f"invalid channel configuration: {channel_id}") from error
    if config.id != channel_id:
        raise ChannelConfigurationError("channel configuration id does not match its filename")
    return config
