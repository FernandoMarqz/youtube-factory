"""Render a previously persisted project without invoking upstream providers."""

import re
from dataclasses import replace
from pathlib import Path

from youtube_factory.application.config import (
    AudioConfig,
    CaptionConfig,
    RenderConfig,
    VisualMotionConfig,
    VisualPacingConfig,
)
from youtube_factory.application.exceptions import (
    CaptionArtifactError,
    MusicSelectionError,
    RenderValidationError,
)
from youtube_factory.application.services.captions import build_ass
from youtube_factory.application.services.music import (
    DeterministicCatalogMusicSelector,
    MusicSelector,
    load_music_catalog,
)
from youtube_factory.application.services.visual_motion import DeterministicVisualMotionPlanner
from youtube_factory.application.services.visual_pacing import DeterministicVisualPacingPlanner
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
        catalog_root: Path | None = None,
        music_selector: MusicSelector | None = None,
        visual_motion: VisualMotionConfig | None = None,
        visual_pacing: VisualPacingConfig | None = None,
    ) -> None:
        self._artifact_store = artifact_store
        self._renderer = renderer
        self._config = config
        self._captions = captions
        self._audio = audio
        self._catalog_root = catalog_root or Path(__file__).resolve().parents[4]
        self._music_selector = music_selector or DeterministicCatalogMusicSelector()
        self._visual_motion = visual_motion
        self._visual_pacing = visual_pacing

    def execute(self, project_id: str, *, reselect_music: bool = False) -> RenderArtifact:
        """Render only; no research, script, TTS, or image provider is contacted."""
        inputs = self._artifact_store.load_render_inputs(project_id)
        if self._audio is not None:
            inputs = replace(inputs, audio=self._audio)
            music = self._audio.music
            if reselect_music and (not music.enabled or music.mode != "catalog"):
                raise MusicSelectionError("--reselect-music requires enabled catalog music")
            if music.enabled and music.mode == "catalog":
                selection = (
                    None
                    if reselect_music
                    else self._artifact_store.load_music_selection(project_id)
                )
                if selection is None:
                    catalog = load_music_catalog(self._catalog_root / music.catalog_path)
                    topic, script = self._artifact_store.load_music_context(project_id)
                    selection, source = self._music_selector.select(
                        catalog, topic, script, music.selection
                    )
                    self._artifact_store.save_music_selection(project_id, selection, source)
                resolved_music = music.model_copy(
                    update={"mode": "manual", "file_path": selection.file_path}
                )
                inputs = replace(
                    inputs,
                    audio=self._audio.model_copy(update={"music": resolved_music}),
                )
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
        if self._visual_motion is not None:
            motion_plan = DeterministicVisualMotionPlanner().plan(
                inputs.timed_scene_plan, inputs.visual_assets, self._visual_motion, self._config.fps
            )
            inputs = replace(inputs, visual_motion=motion_plan)
        if self._visual_pacing is not None:
            if inputs.visual_motion is None or self._visual_motion is None:
                raise RenderValidationError("visual pacing requires a scene-level motion plan")
            pacing_plan = DeterministicVisualPacingPlanner().plan(
                inputs.timed_scene_plan,
                inputs.visual_motion,
                inputs.visual_assets,
                self._visual_pacing,
                self._visual_motion,
            )
            inputs = replace(inputs, visual_pacing=pacing_plan)
        artifact = self._renderer.render(inputs, self._config)
        if inputs.visual_motion is not None:
            self._artifact_store.save_visual_motion(project_id, inputs.visual_motion)
        if inputs.visual_pacing is not None:
            self._artifact_store.save_visual_pacing(project_id, inputs.visual_pacing)
        self._artifact_store.save_render(project_id, artifact, self._renderer.identifier)
        return artifact
