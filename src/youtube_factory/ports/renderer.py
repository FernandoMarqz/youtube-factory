"""Provider-neutral rendering boundary."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from youtube_factory.application.config import AudioConfig, RenderConfig
from youtube_factory.domain.models import (
    HybridVisualCompositionPlan,
    Narration,
    RenderArtifact,
    TimedScenePlan,
    VisualAssetManifest,
    VisualMotionPlan,
    VisualPacingPlan,
)


@dataclass(frozen=True, slots=True)
class RenderInputs:
    """Validated persisted media and its project-local filesystem location."""

    project_directory: Path
    narration: Narration
    timed_scene_plan: TimedScenePlan
    visual_assets: VisualAssetManifest
    caption_ass_path: str | None = None
    audio: AudioConfig = field(default_factory=AudioConfig)
    visual_motion: VisualMotionPlan | None = None
    visual_pacing: VisualPacingPlan | None = None
    hybrid_visuals: HybridVisualCompositionPlan | None = None


class Renderer(Protocol):
    """Turn prepared, persisted media into a measured video artifact."""

    provider: str
    identifier: str

    def render(self, inputs: RenderInputs, config: RenderConfig) -> RenderArtifact:
        """Render and validate one project video."""
