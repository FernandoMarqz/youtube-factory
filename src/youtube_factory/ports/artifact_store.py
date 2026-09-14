"""Artifact persistence boundary."""

from pathlib import Path
from typing import Protocol

from youtube_factory.domain.models import ContentManifest, ResearchResult, ScenePlan, Script, Topic


class ProjectArtifactStore(Protocol):
    """Persists inspectable content-pipeline artifacts for a project."""

    def save(
        self,
        project_id: str,
        topic: Topic,
        research: ResearchResult,
        script: Script,
        scene_plan: ScenePlan,
        manifest: ContentManifest,
    ) -> Path:
        """Write all artifacts and return the project directory."""
