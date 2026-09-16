"""Render a previously persisted project without invoking upstream providers."""

import re
from dataclasses import replace

from youtube_factory.application.config import AudioConfig, CaptionConfig, RenderConfig
from youtube_factory.application.exceptions import CaptionArtifactError
from youtube_factory.application.services.captions import build_ass
from youtube_factory.domain.models import RenderArtifact
from youtube_factory.ports import ProjectArtifactStore, Renderer


class RenderProjectUseCase:
    """Coordinate persisted input loading, rendering, and metadata persistence."""

    def __init__(
        self,
        artifact_store: ProjectArtifactStore,
        renderer: Renderer,
        config: RenderConfig,
        captions: CaptionConfig | None = None,
        audio: AudioConfig | None = None,
    ) -> None:
        self._artifact_store = artifact_store
        self._renderer = renderer
        self._config = config
        self._captions = captions
        self._audio = audio

    def execute(self, project_id: str) -> RenderArtifact:
        """Render only; no research, script, TTS, or image provider is contacted."""
        inputs = self._artifact_store.load_render_inputs(project_id)
        if self._audio is not None:
            inputs = replace(inputs, audio=self._audio)
        if self._captions is not None and self._captions.enabled:
            plan = self._artifact_store.load_caption_plan(project_id)
            if plan is not None:
                if plan.topic_id != inputs.narration.topic_id:
                    raise CaptionArtifactError("caption plan belongs to a different topic")
                if plan.cues[
                    -1
                ].end_seconds > inputs.narration.duration_seconds + 0.1 or re.findall(
                    r"\S+", " ".join(cue.text for cue in plan.cues)
                ) != re.findall(r"\S+", inputs.narration.narration_text):
                    raise CaptionArtifactError("caption plan differs from persisted narration")
                emphasis = self._captions.emphasis
                alignment = (
                    self._artifact_store.load_word_alignment(project_id)
                    if emphasis.enabled and emphasis.mode == "word"
                    else None
                )
                ass = build_ass(
                    plan,
                    self._captions.style,
                    self._config.width,
                    self._config.height,
                    self._captions.grouping.max_characters_per_line,
                    alignment=alignment,
                    emphasis=emphasis,
                )
                self._artifact_store.save_caption_ass(project_id, ass)
                inputs = replace(inputs, caption_ass_path="captions/captions.ass")
        artifact = self._renderer.render(inputs, self._config)
        self._artifact_store.save_render(project_id, artifact, self._renderer.identifier)
        return artifact
