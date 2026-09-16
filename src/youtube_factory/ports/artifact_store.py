"""Artifact persistence boundary."""

from pathlib import Path
from typing import Protocol

from youtube_factory.domain.models import (
    CaptionPlan,
    ContentManifest,
    Narration,
    RenderArtifact,
    ResearchResult,
    ScenePlan,
    Script,
    TimedScenePlan,
    Topic,
    VisualAssetManifest,
    VisualPromptPlan,
    WordAlignment,
)
from youtube_factory.ports.renderer import RenderInputs
from youtube_factory.ports.visuals import GeneratedVisualAsset


class ProjectArtifactStore(Protocol):
    """Persists inspectable content-pipeline artifacts for a project."""

    def save(
        self,
        project_id: str,
        topic: Topic,
        research: ResearchResult,
        script: Script,
        scene_plan: ScenePlan,
        narration: Narration,
        narration_audio: bytes,
        timed_scene_plan: TimedScenePlan,
        visual_prompt_plan: VisualPromptPlan,
        visual_asset_manifest: VisualAssetManifest,
        generated_visual_assets: tuple[GeneratedVisualAsset, ...],
        manifest: ContentManifest,
    ) -> Path:
        """Write all artifacts and return the project directory."""

    def load_render_inputs(self, project_id: str) -> RenderInputs:
        """Read the persisted render inputs and resolve their project directory."""

    def save_render(
        self, project_id: str, artifact: RenderArtifact, renderer_identifier: str
    ) -> None:
        """Persist measured render metadata and extend the project manifest."""

    def load_caption_audio(self, project_id: str) -> tuple[Narration, bytes]:
        """Read validated persisted narration metadata and WAV."""

    def save_captions(
        self,
        project_id: str,
        alignment: WordAlignment,
        plan: CaptionPlan,
        ass_text: str,
        identifier: str,
        planner_identifier: str,
    ) -> None:
        """Persist semantic and derived caption artifacts plus manifest metadata."""

    def load_caption_plan(self, project_id: str) -> CaptionPlan | None:
        """Return an existing semantic caption plan, if present."""

    def save_caption_ass(self, project_id: str, ass_text: str) -> None:
        """Regenerate styled ASS from an existing plan without realignment."""
