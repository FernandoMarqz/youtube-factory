"""Pydantic contracts exchanged between pipeline stages."""

from __future__ import annotations

from datetime import datetime
from math import isclose
from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from youtube_factory.domain.enums import (
    AssetSourceType,
    AssetType,
    HookType,
    ProjectStatus,
    RenderStatus,
)

NonEmptyText = Annotated[str, Field(min_length=1)]
PositiveSeconds = Annotated[float, Field(gt=0)]
PositiveSequence = Annotated[int, Field(ge=1)]


class DomainModel(BaseModel):
    """Immutable base model with strict input validation."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Topic(DomainModel):
    """A content idea supplied to the pipeline."""

    id: UUID = Field(default_factory=uuid4)
    title: NonEmptyText
    language: Annotated[str, Field(pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")] = "es"
    category: NonEmptyText = "engineering_curiosities"
    created_at: datetime = Field(default_factory=datetime.now)


class Source(DomainModel):
    """A traceable source supporting research claims."""

    title: NonEmptyText
    url: HttpUrl
    publisher: NonEmptyText
    retrieved_at: datetime = Field(default_factory=datetime.now)
    notes: str | None = None


class ResearchResult(DomainModel):
    """Research findings associated with exactly one topic."""

    topic_id: UUID
    summary: NonEmptyText
    key_facts: list[NonEmptyText] = Field(min_length=1)
    sources: list[Source] = Field(min_length=1)
    uncertainties: list[NonEmptyText] = Field(default_factory=list)


class Script(DomainModel):
    """Structured narration ready to be transformed into scenes."""

    topic_id: UUID
    hook: NonEmptyText
    body: NonEmptyText
    ending: NonEmptyText
    full_narration: NonEmptyText
    hook_type: HookType
    estimated_duration_seconds: PositiveSeconds
    claims: list[NonEmptyText] = Field(min_length=1)


class NarrationGeneratorMetadata(DomainModel):
    """Provider-neutral narration context retained in a project manifest."""

    provider: NonEmptyText
    model: NonEmptyText | None = None
    voice: NonEmptyText
    duration_seconds: PositiveSeconds


class ScenePlannerMetadata(DomainModel):
    """Provider-neutral scene-planner identity retained in the project manifest."""

    provider: NonEmptyText
    model: NonEmptyText | None = None
    identifier: NonEmptyText


class ResearchProviderMetadata(DomainModel):
    """Provider-neutral research identity retained in a project manifest."""

    provider: NonEmptyText
    model: NonEmptyText | None = None
    identifier: NonEmptyText


class ScriptGeneratorMetadata(DomainModel):
    """Provider-neutral script-generator identity retained in a project manifest."""

    provider: NonEmptyText
    model: NonEmptyText | None = None
    identifier: NonEmptyText


class VisualAssetGeneratorMetadata(DomainModel):
    """Provider-neutral visual generation context retained in the manifest."""

    provider: NonEmptyText
    model: NonEmptyText | None = None
    asset_count: PositiveSequence


class RendererMetadata(DomainModel):
    """Provider-neutral renderer identity in a project manifest."""

    provider: NonEmptyText
    identifier: NonEmptyText


class VisualMotionMetadata(DomainModel):
    identifier: NonEmptyText
    enabled: bool


class VisualPacingMetadata(DomainModel):
    identifier: NonEmptyText
    enabled: bool


class GenerativeVideoMetadata(DomainModel):
    identifier: NonEmptyText
    provider: NonEmptyText
    generated_asset_count: Annotated[int, Field(ge=0)]


class AudioMixerMetadata(DomainModel):
    provider: NonEmptyText
    identifier: NonEmptyText
    music_enabled: bool


class MusicSelectorMetadata(DomainModel):
    identifier: NonEmptyText
    mode: Annotated[str, Field(pattern=r"^catalog$")]
    track_id: NonEmptyText


class MusicLicense(DomainModel):
    source: NonEmptyText
    source_url: NonEmptyText
    license_type: NonEmptyText
    attribution_required: bool
    attribution_text: str | None = None

    @model_validator(mode="after")
    def valid_attribution(self) -> MusicLicense:
        if self.attribution_required and not self.attribution_text:
            raise ValueError("attribution text is required when attribution is required")
        return self


class MusicSelectionDetails(DomainModel):
    mode: Annotated[str, Field(pattern=r"^catalog$")]
    score: int
    matched_moods: tuple[str, ...] = ()
    matched_topics: tuple[str, ...] = ()
    profile: str | None = None
    matched_profiles: tuple[str, ...] = ()
    matched_keywords: tuple[str, ...] = ()
    inferred_topics: tuple[str, ...] = ()
    inferred_moods: tuple[str, ...] = ()
    inferred_niches: tuple[str, ...] = ()
    inferred_genres: tuple[str, ...] = ()
    inferred_energy: str | None = None


class SelectedMusicTrack(DomainModel):
    track_id: NonEmptyText
    title: NonEmptyText
    artist: NonEmptyText
    file_path: NonEmptyText
    catalog_file_path: NonEmptyText
    selection: MusicSelectionDetails
    license: MusicLicense

    @model_validator(mode="after")
    def valid_file_path(self) -> SelectedMusicTrack:
        path = PurePosixPath(self.file_path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in self.file_path
            or ":" in self.file_path
        ):
            raise ValueError("selected music path must be project-relative")
        return self


class CaptionAlignmentMetadata(DomainModel):
    provider: NonEmptyText
    model: NonEmptyText | None = None
    identifier: NonEmptyText


class CaptionPlannerMetadata(DomainModel):
    identifier: NonEmptyText
    cue_count: PositiveSequence


class AlignedWord(DomainModel):
    text: NonEmptyText
    start_seconds: Annotated[float, Field(ge=0)]
    end_seconds: PositiveSeconds

    @model_validator(mode="after")
    def valid_interval(self) -> AlignedWord:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("aligned word end must exceed start")
        return self


class WordAlignment(DomainModel):
    topic_id: UUID
    provider: NonEmptyText
    model: NonEmptyText | None = None
    duration_seconds: PositiveSeconds
    words: list[AlignedWord] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_timeline(self) -> WordAlignment:
        for previous, current in zip(self.words, self.words[1:], strict=False):
            if (
                current.start_seconds < previous.start_seconds
                or current.end_seconds < previous.end_seconds
            ):
                raise ValueError("aligned words must be chronological")
        if self.words[-1].end_seconds > self.duration_seconds + 0.1:
            raise ValueError("aligned words exceed narration duration")
        return self


class CaptionCue(DomainModel):
    sequence: PositiveSequence
    text: NonEmptyText
    start_seconds: Annotated[float, Field(ge=0)]
    end_seconds: PositiveSeconds
    word_start_index: Annotated[int, Field(ge=0)] | None = None
    word_end_index: Annotated[int, Field(gt=0)] | None = None

    @model_validator(mode="after")
    def valid_interval(self) -> CaptionCue:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("caption cue end must exceed start")
        if (self.word_start_index is None) != (self.word_end_index is None):
            raise ValueError("caption cue word indexes must both be present or absent")
        if (
            self.word_start_index is not None
            and self.word_end_index is not None
            and self.word_end_index <= self.word_start_index
        ):
            raise ValueError("caption cue word end index must exceed start index")
        return self


class CaptionPlan(DomainModel):
    topic_id: UUID
    language: NonEmptyText
    cues: list[CaptionCue] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_order(self) -> CaptionPlan:
        if [cue.sequence for cue in self.cues] != list(range(1, len(self.cues) + 1)):
            raise ValueError("caption cue sequences must start at 1 and be contiguous")
        for previous, current in zip(self.cues, self.cues[1:], strict=False):
            if current.start_seconds < previous.end_seconds - 0.001:
                raise ValueError("caption cues must not overlap")
        indexed = [cue.word_start_index is not None for cue in self.cues]
        if any(indexed) and not all(indexed):
            raise ValueError("caption cue word indexes must be present for every cue")
        if all(indexed):
            expected_start = 0
            for cue in self.cues:
                if cue.word_start_index != expected_start or cue.word_end_index is None:
                    raise ValueError("caption cue word indexes must be contiguous")
                expected_start = cue.word_end_index
        return self


class AudioMixReport(DomainModel):
    """Measured final audio and the deterministic mix settings used to produce it."""

    provider: NonEmptyText
    identifier: NonEmptyText
    normalization_enabled: bool
    target_lufs: float
    true_peak_limit_db: float
    narration_input_lufs: float | None = None
    narration_was_silent: bool
    music_enabled: bool
    music_file_path: str | None = None
    music_gain_db: float | None = None
    music_loop: bool | None = None
    ducking_enabled: bool
    final_integrated_lufs: float | None = None
    final_true_peak_db: float | None = None
    sample_rate_hz: Annotated[int, Field(gt=0)]
    channels: Annotated[int, Field(gt=0)]


class RenderArtifact(DomainModel):
    """Measured properties of a persisted rendered video."""

    provider: NonEmptyText
    file_path: NonEmptyText
    media_type: Annotated[str, Field(pattern=r"^video/mp4$")] = "video/mp4"
    duration_seconds: PositiveSeconds
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    frame_rate: PositiveSeconds
    video_codec: NonEmptyText
    audio_codec: NonEmptyText
    pixel_format: NonEmptyText
    file_size_bytes: Annotated[int, Field(gt=0)]
    audio_sample_rate_hz: Annotated[int, Field(gt=0)] | None = None
    audio_channels: Annotated[int, Field(gt=0)] | None = None
    audio_mix: AudioMixReport | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def has_project_relative_path(self) -> RenderArtifact:
        path = PurePosixPath(self.file_path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in self.file_path
            or ":" in self.file_path
            or path.as_posix() != self.file_path
        ):
            raise ValueError("render path must be normalized and project-relative")
        if path.suffix.lower() != ".mp4":
            raise ValueError("render artifact must be an MP4")
        return self


class ContentManifest(DomainModel):
    """Stable inventory of artifacts produced by the content foundation pipeline."""

    project_id: UUID
    pipeline_version: NonEmptyText
    channel_id: NonEmptyText
    topic: NonEmptyText
    topic_id: UUID
    artifacts: tuple[NonEmptyText, ...] = Field(min_length=1)
    research_provider: ResearchProviderMetadata
    script_generator: ScriptGeneratorMetadata
    scene_planner: ScenePlannerMetadata | None = None
    narration_generator: NarrationGeneratorMetadata | None = None
    timing_reconciliation_strategy: NonEmptyText | None = None
    visual_asset_generator: VisualAssetGeneratorMetadata | None = None
    renderer: RendererMetadata | None = None
    visual_motion: VisualMotionMetadata | None = None
    visual_pacing: VisualPacingMetadata | None = None
    generative_video: GenerativeVideoMetadata | None = None
    audio_mixer: AudioMixerMetadata | None = None
    music_selector: MusicSelectorMetadata | None = None
    caption_alignment: CaptionAlignmentMetadata | None = None
    caption_planner: CaptionPlannerMetadata | None = None


class Scene(DomainModel):
    """One ordered, timed visual segment."""

    sequence: PositiveSequence
    narration_segment: NonEmptyText
    start_seconds: Annotated[float, Field(ge=0)]
    end_seconds: PositiveSeconds
    visual_description: NonEmptyText
    visual_intent: NonEmptyText
    duration_seconds: PositiveSeconds
    asset_type: AssetType
    on_screen_text: str | None = None
    transition_suggestion: str | None = None

    @model_validator(mode="after")
    def has_consistent_timing(self) -> Scene:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("scene end time must be greater than its start time")
        if not isclose(
            self.duration_seconds,
            self.end_seconds - self.start_seconds,
            rel_tol=0.0,
            abs_tol=0.001,
        ):
            raise ValueError("scene duration must equal end time minus start time")
        return self


class ScenePlan(DomainModel):
    """An ordered visual interpretation of a script."""

    topic_id: UUID
    scenes: list[Scene] = Field(min_length=1)
    total_duration_seconds: PositiveSeconds

    @model_validator(mode="after")
    def has_contiguous_scene_sequences(self) -> ScenePlan:
        _validate_timeline(self.scenes, self.total_duration_seconds)
        return self


def _validate_timeline(scenes: list[Scene], total_duration_seconds: float) -> None:
    """Validate sequence order, continuity and total duration shared by both timeline contracts."""
    sequences = [scene.sequence for scene in scenes]
    expected = list(range(1, len(scenes) + 1))
    if sequences != expected:
        raise ValueError("scene sequences must be contiguous and start at 1")
    if not isclose(scenes[0].start_seconds, 0.0, rel_tol=0.0, abs_tol=0.001):
        raise ValueError("scene timeline must start at 0 seconds")
    for previous, current in zip(scenes, scenes[1:], strict=False):
        if not isclose(
            previous.end_seconds,
            current.start_seconds,
            rel_tol=0.0,
            abs_tol=0.001,
        ):
            raise ValueError("scene timeline must be continuous without gaps or overlaps")
    if not isclose(
        scenes[-1].end_seconds,
        total_duration_seconds,
        rel_tol=0.0,
        abs_tol=0.001,
    ):
        raise ValueError("total duration must match the final scene end time")


class Narration(DomainModel):
    """The recorded narration artifact for a script."""

    topic_id: UUID
    file_path: NonEmptyText
    duration_seconds: PositiveSeconds
    provider: NonEmptyText
    voice: NonEmptyText
    audio_format: Annotated[str, Field(pattern=r"^[a-z0-9]+$")] = "wav"
    sample_rate_hz: Annotated[int, Field(gt=0)]
    narration_text: NonEmptyText
    script_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    model: NonEmptyText | None = None
    input_character_count: Annotated[int, Field(gt=0)] | None = None


class TimedScenePlan(DomainModel):
    """Render-ready timeline reconciled against an authoritative narration duration."""

    topic_id: UUID
    source_total_duration_seconds: PositiveSeconds
    narration_duration_seconds: PositiveSeconds
    total_duration_seconds: PositiveSeconds
    reconciliation_strategy: NonEmptyText
    scenes: list[Scene] = Field(min_length=1)

    @model_validator(mode="after")
    def has_narration_aligned_timeline(self) -> TimedScenePlan:
        _validate_timeline(self.scenes, self.total_duration_seconds)
        if not isclose(
            self.total_duration_seconds,
            self.narration_duration_seconds,
            rel_tol=0.0,
            abs_tol=0.001,
        ):
            raise ValueError("timed plan duration must match narration duration")
        return self


MotionType = Literal[
    "static",
    "slow_zoom_in",
    "slow_zoom_out",
    "pan_left",
    "pan_right",
    "pan_up",
    "pan_down",
    "pan_zoom_in",
    "pan_zoom_out",
]


class SceneMotion(DomainModel):
    scene_sequence: PositiveSequence
    motion_type: MotionType
    duration_seconds: PositiveSeconds
    start_zoom: Annotated[float, Field(ge=1.0, le=1.2)]
    end_zoom: Annotated[float, Field(ge=1.0, le=1.2)]
    pan_x_start: Annotated[float, Field(ge=0, le=1)] = 0.5
    pan_x_end: Annotated[float, Field(ge=0, le=1)] = 0.5
    pan_y_start: Annotated[float, Field(ge=0, le=1)] = 0.5
    pan_y_end: Annotated[float, Field(ge=0, le=1)] = 0.5
    transition_type: Literal["cut"] = "cut"


class VisualMotionPlan(DomainModel):
    identifier: NonEmptyText
    topic_id: UUID
    fps: Annotated[int, Field(gt=0)]
    enabled: bool
    scenes: list[SceneMotion] = Field(min_length=1)

    @model_validator(mode="after")
    def ordered_scenes(self) -> VisualMotionPlan:
        if [scene.scene_sequence for scene in self.scenes] != list(range(1, len(self.scenes) + 1)):
            raise ValueError("motion scenes must be contiguous and ordered")
        return self


class VisualBeat(SceneMotion):
    """One frame-exact camera interval using its parent scene's PNG."""

    beat_sequence: PositiveSequence
    start_frame: Annotated[int, Field(ge=0)]
    end_frame: Annotated[int, Field(gt=0)]
    frame_count: PositiveSequence

    @model_validator(mode="after")
    def consistent_frames(self) -> VisualBeat:
        if self.end_frame - self.start_frame != self.frame_count:
            raise ValueError("visual beat frame count does not match its boundaries")
        return self


class SceneVisualPacing(DomainModel):
    scene_sequence: PositiveSequence
    start_frame: Annotated[int, Field(ge=0)]
    end_frame: Annotated[int, Field(gt=0)]
    beats: list[VisualBeat] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def contiguous_beats(self) -> SceneVisualPacing:
        if self.beats[0].start_frame != self.start_frame:
            raise ValueError("first visual beat must start at its scene boundary")
        if self.beats[-1].end_frame != self.end_frame:
            raise ValueError("last visual beat must end at its scene boundary")
        if [beat.beat_sequence for beat in self.beats] != list(range(1, len(self.beats) + 1)):
            raise ValueError("visual beat sequences must be ordered")
        if any(beat.scene_sequence != self.scene_sequence for beat in self.beats):
            raise ValueError("visual beats belong to a different scene")
        if any(
            left.end_frame != right.start_frame
            for left, right in zip(self.beats, self.beats[1:], strict=False)
        ):
            raise ValueError("visual beats must have no frame gaps or overlaps")
        return self


class VisualPacingPlan(DomainModel):
    identifier: NonEmptyText
    topic_id: UUID
    fps: Annotated[int, Field(gt=0)]
    enabled: bool
    scenes: list[SceneVisualPacing] = Field(min_length=1)

    @model_validator(mode="after")
    def contiguous_scenes(self) -> VisualPacingPlan:
        if [scene.scene_sequence for scene in self.scenes] != list(range(1, len(self.scenes) + 1)):
            raise ValueError("visual pacing scenes must be ordered")
        if self.scenes[0].start_frame != 0:
            raise ValueError("visual pacing must start at frame zero")
        if any(
            left.end_frame != right.start_frame
            for left, right in zip(self.scenes, self.scenes[1:], strict=False)
        ):
            raise ValueError("visual pacing scenes must be frame-contiguous")
        for scene in self.scenes:
            for beat in scene.beats:
                if not isclose(beat.duration_seconds, beat.frame_count / self.fps, abs_tol=0.001):
                    raise ValueError("visual beat duration must match frame count")
        return self


class PlannedVideoScene(DomainModel):
    scene_sequence: PositiveSequence
    eligible: bool
    selected: bool
    score: Annotated[int, Field(ge=0)]
    source_asset: NonEmptyText
    target_duration_seconds: Annotated[int, Field(ge=0)] = 0
    reasons: tuple[str, ...] = ()
    prompt: str | None = None


class GenerativeVideoPlan(DomainModel):
    identifier: NonEmptyText
    topic_id: UUID
    provider: NonEmptyText
    model: NonEmptyText
    max_generated_scenes: Annotated[int, Field(ge=0)]
    max_generated_seconds: Annotated[int, Field(ge=0)]
    scenes: list[PlannedVideoScene]

    @model_validator(mode="after")
    def within_budget(self) -> GenerativeVideoPlan:
        selected = [scene for scene in self.scenes if scene.selected]
        if (
            len(selected) > self.max_generated_scenes
            or sum(scene.target_duration_seconds for scene in selected) > self.max_generated_seconds
        ):
            raise ValueError("generative video plan exceeds configured budget")
        if any(not scene.eligible for scene in selected):
            raise ValueError("selected generative scene must be eligible")
        return self


class GeneratedVideoAsset(DomainModel):
    scene_sequence: PositiveSequence
    provider: NonEmptyText
    model: NonEmptyText
    file_path: NonEmptyText
    source_image: NonEmptyText
    reference_image: NonEmptyText
    duration_seconds: PositiveSeconds
    width: PositiveSequence
    height: PositiveSequence
    fps: PositiveSeconds
    video_codec: NonEmptyText
    has_audio: bool
    requested_seconds: PositiveSequence
    provider_task_id: NonEmptyText
    prompt_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    source_image_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    requested_at: datetime
    completed_at: datetime

    @model_validator(mode="after")
    def relative_paths(self) -> GeneratedVideoAsset:
        for value in (self.file_path, self.source_image, self.reference_image):
            path = PurePosixPath(value)
            if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
                raise ValueError("generated video paths must be project-relative")
        return self


class GeneratedVideoManifest(DomainModel):
    topic_id: UUID
    provider: NonEmptyText
    model: NonEmptyText
    assets: list[GeneratedVideoAsset]

    @model_validator(mode="after")
    def unique_scenes(self) -> GeneratedVideoManifest:
        sequences = [asset.scene_sequence for asset in self.assets]
        if len(sequences) != len(set(sequences)):
            raise ValueError("generated video scenes must be unique")
        return self


class HybridVisualSegment(DomainModel):
    scene_sequence: PositiveSequence
    beat_sequence: PositiveSequence
    start_frame: Annotated[int, Field(ge=0)]
    end_frame: Annotated[int, Field(gt=0)]
    generated_file_path: NonEmptyText


class HybridVisualCompositionPlan(DomainModel):
    topic_id: UUID
    fps: PositiveSequence
    segments: list[HybridVisualSegment]


class VisualPrompt(DomainModel):
    """A provider-ready image instruction derived from one timed scene."""

    scene_sequence: PositiveSequence
    prompt: NonEmptyText
    exclusions: NonEmptyText | None = None
    visual_intent: NonEmptyText
    asset_type: AssetType
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    aspect_ratio: NonEmptyText
    style: NonEmptyText


class VisualPromptPlan(DomainModel):
    """Ordered generation-ready visual instructions for a timed scene plan."""

    topic_id: UUID
    channel_id: NonEmptyText
    prompts: list[VisualPrompt] = Field(min_length=1)

    @model_validator(mode="after")
    def has_ordered_unique_prompts(self) -> VisualPromptPlan:
        sequences = [prompt.scene_sequence for prompt in self.prompts]
        if sequences != list(range(1, len(self.prompts) + 1)):
            raise ValueError("visual prompt sequences must be contiguous and start at 1")
        return self


class VisualAsset(DomainModel):
    """Metadata for one persisted provider-neutral PNG assigned to a scene."""

    scene_sequence: PositiveSequence
    provider: NonEmptyText
    model: NonEmptyText | None = None
    file_path: NonEmptyText
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    media_type: Annotated[str, Field(pattern=r"^image/png$")] = "image/png"
    prompt_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    revised_prompt: NonEmptyText | None = None

    @model_validator(mode="after")
    def has_relative_project_path(self) -> VisualAsset:
        path = PurePosixPath(self.file_path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or path.as_posix() != self.file_path
            or path.suffix.lower() != ".png"
        ):
            raise ValueError("visual asset path must be a normalized project-relative path")
        return self


class VisualAssetManifest(DomainModel):
    """Inventory connecting each scene to its generated visual asset."""

    topic_id: UUID
    channel_id: NonEmptyText
    provider: NonEmptyText
    model: NonEmptyText | None = None
    assets: list[VisualAsset] = Field(min_length=1)

    @model_validator(mode="after")
    def has_consistent_ordered_assets(self) -> VisualAssetManifest:
        sequences = [asset.scene_sequence for asset in self.assets]
        if sequences != list(range(1, len(self.assets) + 1)):
            raise ValueError("visual asset sequences must be contiguous and start at 1")
        if any(asset.provider != self.provider for asset in self.assets):
            raise ValueError("visual assets must match the manifest provider")
        if any(asset.model != self.model for asset in self.assets):
            raise ValueError("visual assets must match the manifest model")
        return self


class Asset(DomainModel):
    """A local visual asset assigned to a specific scene."""

    topic_id: UUID
    scene_sequence: PositiveSequence
    file_path: NonEmptyText
    asset_type: AssetType
    source_type: AssetSourceType
    metadata: dict[str, str] = Field(default_factory=dict)


class RenderJob(DomainModel):
    """A request to render a short from its prepared artifacts."""

    id: UUID = Field(default_factory=uuid4)
    topic_id: UUID
    status: RenderStatus = RenderStatus.PENDING
    output_path: NonEmptyText
    created_at: datetime = Field(default_factory=datetime.now)


class RenderResult(DomainModel):
    """Properties of a successfully rendered video artifact."""

    job_id: UUID
    output_path: NonEmptyText
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    duration_seconds: PositiveSeconds
    fps: PositiveSeconds

    @model_validator(mode="after")
    def is_vertical_video(self) -> RenderResult:
        if self.height <= self.width:
            raise ValueError("rendered video must use a vertical aspect ratio")
        return self


class ShortProject(DomainModel):
    """The inspectable aggregate for one Short production run."""

    id: UUID = Field(default_factory=uuid4)
    topic: Topic
    status: ProjectStatus = ProjectStatus.DRAFT
    working_directory: NonEmptyText
    created_at: datetime = Field(default_factory=datetime.now)
    research: ResearchResult | None = None
    script: Script | None = None
    scene_plan: ScenePlan | None = None
    narration: Narration | None = None
    assets: list[Asset] = Field(default_factory=list)
    render_job: RenderJob | None = None
    render_result: RenderResult | None = None

    @model_validator(mode="after")
    def artifacts_belong_to_project_topic(self) -> ShortProject:
        topic_id = self.topic.id
        artifacts = [self.research, self.script, self.scene_plan, self.narration, self.render_job]
        if any(artifact is not None and artifact.topic_id != topic_id for artifact in artifacts):
            raise ValueError("all artifacts must belong to the project's topic")
        if any(asset.topic_id != topic_id for asset in self.assets):
            raise ValueError("all assets must belong to the project's topic")
        return self
