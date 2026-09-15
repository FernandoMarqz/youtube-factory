"""Local JSON artifact persistence for Phase 1."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from youtube_factory.application.exceptions import ArtifactPersistenceError
from youtube_factory.domain.models import (
    ContentManifest,
    Narration,
    ResearchResult,
    ScenePlan,
    Script,
    TimedScenePlan,
    Topic,
    VisualAssetManifest,
    VisualPromptPlan,
)
from youtube_factory.ports import GeneratedVisualAsset


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
