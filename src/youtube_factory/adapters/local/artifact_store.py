"""Local JSON artifact persistence for Phase 1."""

import json
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from youtube_factory.application.exceptions import (
    ArtifactPersistenceError,
    CaptionArtifactError,
    InvalidAudioArtifactError,
    MusicSelectionError,
    RenderValidationError,
    VisualAssetValidationError,
)
from youtube_factory.application.services import validate_png, validate_wav_narration
from youtube_factory.domain.models import (
    AudioMixerMetadata,
    CaptionAlignmentMetadata,
    CaptionPlan,
    CaptionPlannerMetadata,
    ContentManifest,
    MusicSelectorMetadata,
    Narration,
    RenderArtifact,
    RendererMetadata,
    ResearchResult,
    ScenePlan,
    Script,
    SelectedMusicTrack,
    TimedScenePlan,
    Topic,
    VisualAssetManifest,
    VisualMotionMetadata,
    VisualMotionPlan,
    VisualPacingMetadata,
    VisualPacingPlan,
    VisualPromptPlan,
    WordAlignment,
)
from youtube_factory.ports import GeneratedVisualAsset
from youtube_factory.ports.renderer import RenderInputs


class FileSystemArtifactStore:
    """Writes stable, human-readable JSON into one deterministic project directory."""

    def __init__(self, root_directory: Path) -> None:
        self._root_directory = root_directory

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
        """Persist all Phase 1 artifacts and return their project directory."""
        project_directory = self._root_directory / project_id
        try:
            project_directory.mkdir(parents=True, exist_ok=True)
            self._write_model(project_directory / "topic.json", topic)
            self._write_model(project_directory / "research.json", research)
            self._write_model(project_directory / "script.json", script)
            self._write_model(project_directory / "scenes.json", scene_plan)
            self._write_model(project_directory / "narration.json", narration)
            (project_directory / narration.file_path).write_bytes(narration_audio)
            self._write_model(project_directory / "timed-scenes.json", timed_scene_plan)
            self._write_model(project_directory / "visual-prompts.json", visual_prompt_plan)
            for generated in generated_visual_assets:
                asset_path = project_directory / generated.asset.file_path
                asset_path.parent.mkdir(parents=True, exist_ok=True)
                asset_path.write_bytes(generated.image_bytes)
            self._write_model(project_directory / "visual-assets.json", visual_asset_manifest)
            self._write_model(project_directory / "manifest.json", manifest)
        except OSError as error:
            raise ArtifactPersistenceError("could not write project artifacts") from error
        return project_directory

    @staticmethod
    def _write_model(path: Path, model: BaseModel) -> None:
        payload: dict[str, Any] = model.model_dump(mode="json")
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def load_render_inputs(self, project_id: str) -> RenderInputs:
        """Load and validate the persisted WAV, timed plan and one PNG per scene."""
        directory = self._project_directory(project_id)
        try:
            narration = Narration.model_validate_json(
                (directory / "narration.json").read_text("utf-8")
            )
            timed = TimedScenePlan.model_validate_json(
                (directory / "timed-scenes.json").read_text("utf-8")
            )
            visuals = VisualAssetManifest.model_validate_json(
                (directory / "visual-assets.json").read_text("utf-8")
            )
            if not (narration.topic_id == timed.topic_id == visuals.topic_id):
                raise RenderValidationError("render input topic ids do not match")
            if len(timed.scenes) != len(visuals.assets):
                raise RenderValidationError("timed scene and visual asset counts differ")
            if abs(narration.duration_seconds - timed.total_duration_seconds) > 0.001:
                raise RenderValidationError("timed plan does not match narration duration")
            audio_path = self._resolve_project_path(directory, narration.file_path)
            validate_wav_narration(narration, audio_path.read_bytes())
            for scene, asset in zip(timed.scenes, visuals.assets, strict=True):
                if scene.sequence != asset.scene_sequence:
                    raise RenderValidationError("scene and asset sequences do not match")
                image_path = self._resolve_project_path(directory, asset.file_path)
                if validate_png(image_path.read_bytes()) != (asset.width, asset.height):
                    raise RenderValidationError(f"PNG dimensions differ for scene {scene.sequence}")
        except (
            OSError,
            ValueError,
            VisualAssetValidationError,
            InvalidAudioArtifactError,
        ) as error:
            raise RenderValidationError(f"missing or invalid render input: {error}") from error
        return RenderInputs(directory, narration, timed, visuals)

    def save_render(
        self, project_id: str, artifact: RenderArtifact, renderer_identifier: str
    ) -> None:
        """Write render metadata after the renderer has produced the MP4."""
        directory = self._project_directory(project_id)
        try:
            manifest = ContentManifest.model_validate_json(
                (directory / "manifest.json").read_text("utf-8")
            )
            if not self._resolve_project_path(directory, artifact.file_path).is_file():
                raise RenderValidationError("rendered MP4 is missing")
            updated = manifest.model_copy(
                update={
                    "artifacts": tuple(
                        dict.fromkeys(
                            (
                                *manifest.artifacts,
                                "render.json",
                                artifact.file_path,
                                *(("audio-mix.json",) if artifact.audio_mix else ()),
                            )
                        )
                    ),
                    "renderer": RendererMetadata(
                        provider=artifact.provider, identifier=renderer_identifier
                    ),
                    "audio_mixer": (
                        AudioMixerMetadata(
                            provider=artifact.audio_mix.provider,
                            identifier=artifact.audio_mix.identifier,
                            music_enabled=artifact.audio_mix.music_enabled,
                        )
                        if artifact.audio_mix
                        else manifest.audio_mixer
                    ),
                }
            )
            self._write_model(directory / "render.json", artifact)
            if artifact.audio_mix is not None:
                self._write_model(directory / "audio-mix.json", artifact.audio_mix)
            self._write_model(directory / "manifest.json", updated)
        except OSError as error:
            raise ArtifactPersistenceError("could not persist render metadata") from error

    def save_visual_motion(self, project_id: str, plan: VisualMotionPlan) -> None:
        directory = self._project_directory(project_id)
        try:
            manifest = ContentManifest.model_validate_json(
                (directory / "manifest.json").read_text("utf-8")
            )
            if plan.topic_id != manifest.topic_id:
                raise RenderValidationError("motion plan belongs to a different topic")
            self._write_model(directory / "visual-motion.json", plan)
            updated = manifest.model_copy(
                update={
                    "artifacts": tuple(dict.fromkeys((*manifest.artifacts, "visual-motion.json"))),
                    "visual_motion": VisualMotionMetadata(
                        identifier=plan.identifier, enabled=plan.enabled
                    ),
                }
            )
            self._write_model(directory / "manifest.json", updated)
        except OSError as error:
            raise ArtifactPersistenceError("could not persist visual motion") from error

    def save_visual_pacing(self, project_id: str, plan: VisualPacingPlan) -> None:
        directory = self._project_directory(project_id)
        try:
            manifest = ContentManifest.model_validate_json(
                (directory / "manifest.json").read_text("utf-8")
            )
            if plan.topic_id != manifest.topic_id:
                raise RenderValidationError("visual pacing belongs to a different topic")
            self._write_model(directory / "visual-pacing.json", plan)
            updated = manifest.model_copy(
                update={
                    "artifacts": tuple(dict.fromkeys((*manifest.artifacts, "visual-pacing.json"))),
                    "visual_pacing": VisualPacingMetadata(
                        identifier=plan.identifier, enabled=plan.enabled
                    ),
                }
            )
            self._write_model(directory / "manifest.json", updated)
        except OSError as error:
            raise ArtifactPersistenceError("could not persist visual pacing") from error

    def load_caption_audio(self, project_id: str) -> tuple[Narration, bytes]:
        directory = self._project_directory(project_id)
        try:
            narration = Narration.model_validate_json(
                (directory / "narration.json").read_text("utf-8")
            )
            audio = self._resolve_project_path(directory, narration.file_path).read_bytes()
            validate_wav_narration(narration, audio)
            return narration, audio
        except (OSError, ValueError, InvalidAudioArtifactError) as error:
            raise CaptionArtifactError(f"missing or invalid narration WAV: {error}") from error

    def save_captions(
        self,
        project_id: str,
        alignment: WordAlignment,
        plan: CaptionPlan,
        ass_text: str,
        identifier: str,
        planner_identifier: str,
    ) -> None:
        directory = self._project_directory(project_id)
        try:
            manifest = ContentManifest.model_validate_json(
                (directory / "manifest.json").read_text("utf-8")
            )
            if alignment.topic_id != manifest.topic_id or plan.topic_id != manifest.topic_id:
                raise CaptionArtifactError("caption artifacts belong to a different topic")
            self._write_model(directory / "word-alignment.json", alignment)
            self._write_model(directory / "captions.json", plan)
            self.save_caption_ass(project_id, ass_text)
            updated = manifest.model_copy(
                update={
                    "artifacts": tuple(
                        dict.fromkeys(
                            (
                                *manifest.artifacts,
                                "word-alignment.json",
                                "captions.json",
                                "captions/captions.ass",
                            )
                        )
                    ),
                    "caption_alignment": CaptionAlignmentMetadata(
                        provider=alignment.provider, model=alignment.model, identifier=identifier
                    ),
                    "caption_planner": CaptionPlannerMetadata(
                        identifier=planner_identifier, cue_count=len(plan.cues)
                    ),
                }
            )
            self._write_model(directory / "manifest.json", updated)
        except OSError as error:
            raise CaptionArtifactError("could not persist caption artifacts") from error

    def load_caption_plan(self, project_id: str) -> CaptionPlan | None:
        directory = self._project_directory(project_id)
        path = directory / "captions.json"
        if not path.exists():
            return None
        try:
            return CaptionPlan.model_validate_json(path.read_text("utf-8"))
        except (OSError, ValueError) as error:
            raise CaptionArtifactError(f"invalid caption plan: {error}") from error

    def load_word_alignment(self, project_id: str) -> WordAlignment:
        directory = self._project_directory(project_id)
        try:
            return WordAlignment.model_validate_json(
                (directory / "word-alignment.json").read_text("utf-8")
            )
        except (OSError, ValueError) as error:
            raise CaptionArtifactError(
                "missing or invalid word-alignment.json; run caption-project first"
            ) from error

    def save_caption_ass(self, project_id: str, ass_text: str) -> None:
        directory = self._project_directory(project_id)
        try:
            path = directory / "captions" / "captions.ass"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(ass_text, encoding="utf-8")
        except OSError as error:
            raise CaptionArtifactError("could not write ASS captions") from error

    def load_music_context(self, project_id: str) -> tuple[Topic, Script]:
        directory = self._project_directory(project_id)
        try:
            topic = Topic.model_validate_json((directory / "topic.json").read_text("utf-8"))
            script = Script.model_validate_json((directory / "script.json").read_text("utf-8"))
        except (OSError, ValueError) as error:
            raise MusicSelectionError("topic.json or script.json is missing or invalid") from error
        return topic, script

    def load_music_selection(self, project_id: str) -> SelectedMusicTrack | None:
        directory = self._project_directory(project_id)
        path = directory / "selected-music.json"
        if not path.exists():
            return None
        try:
            selection = SelectedMusicTrack.model_validate_json(path.read_text("utf-8"))
            audio = self._resolve_project_path(directory, selection.file_path)
            if not audio.is_file() or audio.stat().st_size == 0:
                raise MusicSelectionError(
                    f"persisted selected music is missing: {selection.file_path}"
                )
            return selection
        except (OSError, ValueError, RenderValidationError) as error:
            raise MusicSelectionError(
                "selected-music.json is invalid or its audio is missing"
            ) from error

    def save_music_selection(
        self, project_id: str, selection: SelectedMusicTrack, source: Path
    ) -> None:
        directory = self._project_directory(project_id)
        try:
            if not source.is_file() or source.stat().st_size == 0:
                raise MusicSelectionError(f"selected catalog audio is missing: {source}")
            manifest = ContentManifest.model_validate_json(
                (directory / "manifest.json").read_text("utf-8")
            )
            target = self._resolve_project_path(directory, selection.file_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() != target.resolve():
                shutil.copyfile(source, target)
            self._write_model(directory / "selected-music.json", selection)
            updated = manifest.model_copy(
                update={
                    "artifacts": tuple(
                        dict.fromkeys(
                            (*manifest.artifacts, selection.file_path, "selected-music.json")
                        )
                    ),
                    "music_selector": MusicSelectorMetadata(
                        identifier="deterministic-catalog-music-selector-v1",
                        mode="catalog",
                        track_id=selection.track_id,
                    ),
                }
            )
            self._write_model(directory / "manifest.json", updated)
        except (OSError, ValueError, RenderValidationError) as error:
            raise MusicSelectionError("could not persist selected music") from error

    @staticmethod
    def _resolve_project_path(directory: Path, relative: str) -> Path:
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise RenderValidationError("render input path escapes project directory")
        return path

    def _project_directory(self, project_id: str) -> Path:
        try:
            if str(UUID(project_id)) != project_id:
                raise ValueError
        except ValueError as error:
            raise RenderValidationError("project id must be a UUID") from error
        return self._root_directory / project_id
