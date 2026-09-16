"""Render a previously persisted project without invoking upstream providers."""

from youtube_factory.application.config import RenderConfig
from youtube_factory.domain.models import RenderArtifact
from youtube_factory.ports import ProjectArtifactStore, Renderer


class RenderProjectUseCase:
    """Coordinate persisted input loading, rendering, and metadata persistence."""

    def __init__(
        self, artifact_store: ProjectArtifactStore, renderer: Renderer, config: RenderConfig
    ) -> None:
        self._artifact_store = artifact_store
        self._renderer = renderer
        self._config = config

    def execute(self, project_id: str) -> RenderArtifact:
        """Render only; no research, script, TTS, or image provider is contacted."""
        inputs = self._artifact_store.load_render_inputs(project_id)
        artifact = self._renderer.render(inputs, self._config)
        self._artifact_store.save_render(project_id, artifact, self._renderer.identifier)
        return artifact
