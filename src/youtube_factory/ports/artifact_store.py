"""Artifact persistence boundary."""

from pathlib import Path
from typing import Protocol

from youtube_factory.domain.models import (
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
