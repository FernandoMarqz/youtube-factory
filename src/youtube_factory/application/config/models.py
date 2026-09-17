"""Typed, immutable editorial configuration loaded outside the domain."""

from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

NonEmptyText = Annotated[str, Field(min_length=1)]
PositiveInt = Annotated[int, Field(gt=0)]
PositiveFloat = Annotated[float, Field(gt=0)]


def _yaml_tuple(value: object) -> object:
    return tuple(value) if isinstance(value, list) else value


TextTuple = Annotated[tuple[NonEmptyText, ...], BeforeValidator(_yaml_tuple)]


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


class RenderConfig(ChannelConfigModel):
    """One channel's MP4 encoding target."""

    provider: Literal["ffmpeg"]
    width: PositiveInt
    height: PositiveInt
    fps: PositiveInt
    video_codec: NonEmptyText
    audio_codec: NonEmptyText
    audio_bitrate: NonEmptyText
    pixel_format: NonEmptyText

    @model_validator(mode="after")
    def has_encodable_dimensions(self) -> "RenderConfig":
        if self.width % 2 or self.height % 2 or self.height <= self.width:
            raise ValueError("render dimensions must be even and vertical")
        return self


class NarrationAudioConfig(ChannelConfigModel):
    normalize: bool = False
    target_lufs: Annotated[float, Field(ge=-30, le=-10, allow_inf_nan=False)] = -16.0
    true_peak_db: Annotated[float, Field(ge=-9, le=-0.1, allow_inf_nan=False)] = -1.5


class MusicConfig(ChannelConfigModel):
    enabled: bool = False
    mode: Literal["manual", "catalog"] = "manual"
    file_path: NonEmptyText | None = None
    catalog_path: NonEmptyText = "assets/music/catalog.yaml"
    selection: "MusicSelectionConfig" = Field(default_factory=lambda: MusicSelectionConfig())
    gain_db: Annotated[float, Field(ge=-60, le=0, allow_inf_nan=False)] = -22.0
    loop: bool = True
    fade_in_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.6
    fade_out_seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 1.2

    @model_validator(mode="after")
    def valid_music_source(self) -> "MusicConfig":
        if self.enabled and self.mode == "manual" and not self.file_path:
            raise ValueError("enabled manual music requires a file_path")
        if self.mode == "catalog" and self.file_path:
            raise ValueError("catalog music cannot specify a manual file_path")
        catalog = PurePosixPath(self.catalog_path)
        if (
            catalog.is_absolute()
            or ".." in catalog.parts
            or "\\" in self.catalog_path
            or ":" in self.catalog_path
            or catalog.as_posix() != self.catalog_path
        ):
            raise ValueError("music catalog_path must be normalized and repository-relative")
        if self.file_path:
            path = PurePosixPath(self.file_path)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in self.file_path
                or ":" in self.file_path
                or path.as_posix() != self.file_path
            ):
                raise ValueError("music file_path must be normalized and project-relative")
        return self


class MusicKeywordProfile(ChannelConfigModel):
    keywords: TextTuple = Field(min_length=1)
    moods: TextTuple = ()
    suitable_topics: TextTuple = ()
    niches: TextTuple = ()
    energy: Literal["low", "low-medium", "medium", "medium-high", "high"] | None = None
    category: NonEmptyText | None = None


class MusicSelectionConfig(ChannelConfigModel):
    preferred_moods: TextTuple = ()
    preferred_energy: Literal["low", "low-medium", "medium", "medium-high", "high"] = "medium"
    preferred_genres: TextTuple = ()
    preferred_niches: TextTuple = ()
    allow_attribution_required: bool = False
    keyword_profiles: dict[str, MusicKeywordProfile] = Field(default_factory=dict)


class DuckingConfig(ChannelConfigModel):
    enabled: bool = True
    threshold: Annotated[float, Field(ge=0.000976563, le=1, allow_inf_nan=False)] = 0.03
    ratio: Annotated[float, Field(ge=1, le=20, allow_inf_nan=False)] = 8.0
    attack_ms: Annotated[float, Field(ge=0.01, le=2000, allow_inf_nan=False)] = 80.0
    release_ms: Annotated[float, Field(ge=0.01, le=9000, allow_inf_nan=False)] = 350.0


class AudioConfig(ChannelConfigModel):
    narration: NarrationAudioConfig = Field(default_factory=NarrationAudioConfig)
    music: MusicConfig = Field(default_factory=MusicConfig)
    ducking: DuckingConfig = Field(default_factory=DuckingConfig)


class CaptionAlignmentConfig(ChannelConfigModel):
    provider: Literal["local", "openai"] = "local"
    model: NonEmptyText | None = None

    @model_validator(mode="after")
    def has_model_for_openai(self) -> "CaptionAlignmentConfig":
        if self.provider == "openai" and not self.model:
            raise ValueError("OpenAI caption alignment requires a model")
        return self


class CaptionGroupingConfig(ChannelConfigModel):
    max_words_per_cue: PositiveInt = 5
    min_cue_duration_seconds: PositiveFloat = 0.45
    max_cue_duration_seconds: PositiveFloat = 2.5
    max_characters_per_line: PositiveInt = 24

    @model_validator(mode="after")
    def valid_duration_range(self) -> "CaptionGroupingConfig":
        if self.min_cue_duration_seconds > self.max_cue_duration_seconds:
            raise ValueError("minimum caption duration exceeds maximum")
        return self


class CaptionStyleConfig(ChannelConfigModel):
    font_family: NonEmptyText = "Arial"
    font_size: PositiveInt = 64
    bold: bool = True
    max_lines: Literal[1, 2] = 2
    position: Literal["lower-middle"] = "lower-middle"
    margin_vertical: PositiveInt = 450
    outline_width: PositiveFloat = 4
    shadow: bool = True


CaptionColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]


class CaptionEmphasisConfig(ChannelConfigModel):
    enabled: bool = False
    mode: Literal["none", "word"] = "word"
    active_color: CaptionColor = "#FFD54A"
    inactive_color: CaptionColor = "#FFFFFF"


class CaptionConfig(ChannelConfigModel):
    enabled: bool = False
    alignment: CaptionAlignmentConfig = Field(default_factory=CaptionAlignmentConfig)
    grouping: CaptionGroupingConfig = Field(default_factory=CaptionGroupingConfig)
    style: CaptionStyleConfig = Field(default_factory=CaptionStyleConfig)
    emphasis: CaptionEmphasisConfig = Field(default_factory=CaptionEmphasisConfig)


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
    render: RenderConfig
    audio: AudioConfig = Field(default_factory=AudioConfig)
    captions: CaptionConfig = Field(default_factory=CaptionConfig)
    publishing: PublishingConfig
