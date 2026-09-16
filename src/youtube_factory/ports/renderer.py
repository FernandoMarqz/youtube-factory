"""Provider-neutral rendering boundary."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from youtube_factory.application.config import RenderConfig
from youtube_factory.domain.models import (
    Narration,
    RenderArtifact,
    TimedScenePlan,
    VisualAssetManifest,
)


@dataclass(frozen=True, slots=True)
class RenderInputs:
    """Validated persisted media and its project-local filesystem location."""

    project_directory: Path
    narration: Narration
    timed_scene_plan: TimedScenePlan
    visual_assets: VisualAssetManifest


class Renderer(Protocol):
    """Turn prepared, persisted media into a measured video artifact."""

    provider: str
    identifier: str

    def render(self, inputs: RenderInputs, config: RenderConfig) -> RenderArtifact:
        """Render and validate one project video."""
