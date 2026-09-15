"""Typed, immutable editorial configuration loaded outside the domain."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonEmptyText = Annotated[str, Field(min_length=1)]
PositiveInt = Annotated[int, Field(gt=0)]
PositiveFloat = Annotated[float, Field(gt=0)]


class ChannelConfigModel(BaseModel):
    """Base model for immutable, strict channel configuration values."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True, strict=True)


class ContentConfig(ChannelConfigModel):
    """Editorial content preferences for one channel."""

    niche: NonEmptyText
    target_duration_seconds: PositiveInt
    min_duration_seconds: PositiveInt
    max_duration_seconds: PositiveInt

    @model_validator(mode="after")
    def has_ordered_duration_bounds(self) -> "ContentConfig":
        """Ensure the editorial target is inside its accepted range."""
        if (
            not self.min_duration_seconds
            <= self.target_duration_seconds
            <= self.max_duration_seconds
        ):
            raise ValueError("min duration must be less than or equal to target and max duration")
        return self


class NarrationConfig(ChannelConfigModel):
    """Provider-neutral narration preferences chosen by a channel."""

    provider: Literal["local", "openai"]
    model: NonEmptyText | None = None
    voice: NonEmptyText | None = None
    instructions: NonEmptyText | None = None

    @model_validator(mode="after")
    def has_openai_requirements(self) -> "NarrationConfig":
        """Require model, voice and delivery instructions when OpenAI is selected."""
        if self.provider == "openai" and (
            not self.model or not self.voice or not self.instructions
        ):
            raise ValueError("OpenAI narration requires model, voice and instructions")
        return self


class ResearchConfig(ChannelConfigModel):
    """Provider-neutral source-backed research preferences for one channel."""

    provider: Literal["local", "openai"]
    model: NonEmptyText | None = None
    max_sources: PositiveInt

    @model_validator(mode="after")
    def has_openai_requirements(self) -> "ResearchConfig":
        """Require an explicit model when external OpenAI research is selected."""
        if self.provider == "openai" and not self.model:
            raise ValueError("OpenAI research requires a model")
        return self


class ScriptConfig(ChannelConfigModel):
    """Provider-neutral script-generation preferences for one channel."""

    provider: Literal["local", "openai"]
    model: NonEmptyText | None = None

    @model_validator(mode="after")
    def has_openai_requirements(self) -> "ScriptConfig":
        """Require an explicit model when OpenAI script generation is selected."""
        if self.provider == "openai" and not self.model:
            raise ValueError("OpenAI script generation requires a model")
        return self


class ScenePlanningConfig(ChannelConfigModel):
    """Provider-neutral semantic scene-planning preferences for one channel."""

    provider: Literal["local", "openai"]
    model: NonEmptyText | None = None
    min_scenes: PositiveInt
    max_scenes: PositiveInt
    target_scene_duration_seconds: PositiveFloat

    @model_validator(mode="after")
    def has_valid_bounds_and_provider_settings(self) -> "ScenePlanningConfig":
        """Validate scene-count bounds and paid-provider model configuration."""
        if self.max_scenes < self.min_scenes:
            raise ValueError("maximum scene count must be greater than or equal to minimum")
        if self.provider == "openai" and not self.model:
            raise ValueError("OpenAI scene planning requires a model")
        return self


class VisualConfig(ChannelConfigModel):
    """Provider-neutral visual generation preferences for one channel."""

    provider: Literal["local-placeholder", "openai"]
    model: NonEmptyText | None = None
    aspect_ratio: NonEmptyText
    width: PositiveInt
    height: PositiveInt
    style: NonEmptyText

    @model_validator(mode="after")
    def has_openai_requirements(self) -> "VisualConfig":
        """Require a model when the paid OpenAI provider is selected."""
        if self.provider == "openai" and not self.model:
            raise ValueError("OpenAI visuals require a model")
        return self


class PublishingConfig(ChannelConfigModel):
    """Explicit publication policy placeholder; no publisher is implemented yet."""

    enabled: bool


class ChannelConfig(ChannelConfigModel):
    """Complete channel/editorial configuration consumed at application composition time."""

    id: Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    language: NonEmptyText
    content: ContentConfig
    research: ResearchConfig
    script: ScriptConfig
    scene_planning: ScenePlanningConfig
    narration: NarrationConfig
    visuals: VisualConfig
    publishing: PublishingConfig
