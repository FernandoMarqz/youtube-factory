"""Local JSON artifact persistence for Phase 1."""

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from youtube_factory.application.exceptions import (
    ArtifactPersistenceError,
    InvalidAudioArtifactError,
    RenderValidationError,
    VisualAssetValidationError,
)
from youtube_factory.application.services import validate_png, validate_wav_narration
from youtube_factory.domain.models import (
    ContentManifest,
    Narration,
    RenderArtifact,
    RendererMetadata,
    ResearchResult,
    ScenePlan,
    Script,
    TimedScenePlan,
    Topic,
    VisualAssetManifest,
    VisualPromptPlan,
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
                        dict.fromkeys((*manifest.artifacts, "render.json", artifact.file_path))
                    ),
                    "renderer": RendererMetadata(
                        provider=artifact.provider, identifier=renderer_identifier
                    ),
                }
            )
            self._write_model(directory / "render.json", artifact)
            self._write_model(directory / "manifest.json", updated)
        except OSError as error:
            raise ArtifactPersistenceError("could not persist render metadata") from error

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
