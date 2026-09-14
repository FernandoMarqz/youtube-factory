"""Local JSON artifact persistence for Phase 1."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from youtube_factory.application.exceptions import ArtifactPersistenceError
from youtube_factory.domain.models import ContentManifest, ResearchResult, Script, Topic


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
        manifest: ContentManifest,
    ) -> Path:
        """Persist all Phase 1 artifacts and return their project directory."""
        project_directory = self._root_directory / project_id
        try:
            project_directory.mkdir(parents=True, exist_ok=True)
            self._write_model(project_directory / "topic.json", topic)
            self._write_model(project_directory / "research.json", research)
            self._write_model(project_directory / "script.json", script)
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
