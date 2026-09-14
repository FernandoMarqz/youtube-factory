"""Pydantic contracts exchanged between pipeline stages."""

from datetime import datetime
from typing import Annotated
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


class Scene(DomainModel):
    """One ordered, timed visual segment."""

    sequence: PositiveSequence
    narration_segment: NonEmptyText
    visual_description: NonEmptyText
    duration_seconds: PositiveSeconds
    asset_type: AssetType
    on_screen_text: str | None = None


class ScenePlan(DomainModel):
    """An ordered visual interpretation of a script."""

    topic_id: UUID
    scenes: list[Scene] = Field(min_length=1)

    @model_validator(mode="after")
    def has_contiguous_scene_sequences(self) -> "ScenePlan":
        sequences = [scene.sequence for scene in self.scenes]
        expected = list(range(1, len(self.scenes) + 1))
        if sequences != expected:
            raise ValueError("scene sequences must be contiguous and start at 1")
        return self


class Narration(DomainModel):
    """The recorded narration artifact for a script."""

    topic_id: UUID
    file_path: NonEmptyText
    duration_seconds: PositiveSeconds
    provider: NonEmptyText
    voice: NonEmptyText


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
    def is_vertical_video(self) -> "RenderResult":
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
    def artifacts_belong_to_project_topic(self) -> "ShortProject":
        topic_id = self.topic.id
        artifacts = [self.research, self.script, self.scene_plan, self.narration, self.render_job]
        if any(artifact is not None and artifact.topic_id != topic_id for artifact in artifacts):
            raise ValueError("all artifacts must belong to the project's topic")
        if any(asset.topic_id != topic_id for asset in self.assets):
            raise ValueError("all assets must belong to the project's topic")
        return self
