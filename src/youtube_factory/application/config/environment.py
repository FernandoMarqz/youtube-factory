"""Machine-local environment configuration used only by composition roots."""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from youtube_factory.application.exceptions import (
    CaptionConfigurationError,
    NarrationGenerationError,
    ProviderConfigurationError,
    ScenePlannerConfigurationError,
    VisualConfigurationError,
)


def load_local_environment(dotenv_path: Path | None = None) -> bool:
    """Load only the working directory's optional .env without overwriting process variables."""
    local_dotenv_path = dotenv_path if dotenv_path is not None else Path.cwd() / ".env"
    return load_dotenv(dotenv_path=local_dotenv_path, override=False)


def get_openai_api_key(
    required_for: Literal[
        "narration", "research", "scene_planning", "script", "visuals", "caption_alignment"
    ] = "narration",
) -> str:
    """Return the configured API key without logging or persisting its value."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        if required_for == "research":
            raise ProviderConfigurationError(
                "OPENAI_API_KEY is required when research provider is openai"
            )
        if required_for == "script":
            raise ProviderConfigurationError(
                "OPENAI_API_KEY is required when script generator is openai"
            )
        if required_for == "scene_planning":
            raise ScenePlannerConfigurationError(
                "OPENAI_API_KEY is required when scene planner is openai"
            )
        if required_for == "visuals":
            raise VisualConfigurationError(
                "OPENAI_API_KEY is required when visual provider is openai"
            )
        if required_for == "caption_alignment":
            raise CaptionConfigurationError(
                "OPENAI_API_KEY is required when caption alignment provider is openai"
            )
        raise NarrationGenerationError(
            "OPENAI_API_KEY is required when narration provider is openai"
        )
    return api_key


def get_output_directory(default: Path) -> Path:
    """Use an optional machine-local output root while preserving the CLI default."""
    configured_directory = os.environ.get("YOUTUBE_FACTORY_OUTPUT_DIR", "").strip()
    return Path(configured_directory) if configured_directory else default
