"""Configuration services owned by application composition roots."""

from youtube_factory.application.config.environment import (
    get_openai_api_key,
    get_output_directory,
    load_local_environment,
)
from youtube_factory.application.config.loader import load_channel_config
from youtube_factory.application.config.models import (
    AudioConfig,
    CaptionAlignmentConfig,
    CaptionConfig,
    CaptionEmphasisConfig,
    CaptionGroupingConfig,
    CaptionStyleConfig,
    ChannelConfig,
    ContentConfig,
    DuckingConfig,
    MusicConfig,
    NarrationAudioConfig,
    NarrationConfig,
    PublishingConfig,
    RenderConfig,
    ResearchConfig,
    ScenePlanningConfig,
    ScriptConfig,
    VisualConfig,
)

__all__ = [
    "AudioConfig",
    "ChannelConfig",
    "CaptionAlignmentConfig",
    "CaptionConfig",
    "CaptionEmphasisConfig",
    "CaptionGroupingConfig",
    "CaptionStyleConfig",
    "ContentConfig",
    "DuckingConfig",
    "MusicConfig",
    "NarrationAudioConfig",
    "NarrationConfig",
    "PublishingConfig",
    "RenderConfig",
    "ResearchConfig",
    "ScenePlanningConfig",
    "ScriptConfig",
    "VisualConfig",
    "get_openai_api_key",
    "get_output_directory",
    "load_channel_config",
    "load_local_environment",
]
