"""Artifact persistence boundary."""

from pathlib import Path
from typing import Protocol

from youtube_factory.domain.models import (
    ContentManifest,
    Narration,
    ResearchResult,
    ScenePlan,
    Script,
    TimedScenePlan,
    Topic,
)


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
        manifest: ContentManifest,
    ) -> Path:
        """Write all artifacts and return the project directory."""
