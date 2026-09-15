"""Typed, immutable editorial configuration loaded outside the domain."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonEmptyText = Annotated[str, Field(min_length=1)]
PositiveInt = Annotated[int, Field(gt=0)]


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
    narration: NarrationConfig
    visuals: VisualConfig
    publishing: PublishingConfig
