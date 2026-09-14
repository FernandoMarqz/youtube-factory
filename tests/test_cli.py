"""Tests for the bootstrap CLI."""

import subprocess
import sys
from pathlib import Path

from youtube_factory.domain.models import ContentManifest, ResearchResult, Script, Topic


def test_module_status_command() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "youtube_factory", "status"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "youtube-factory bootstrap ready"


def test_create_content_writes_parseable_artifacts(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "youtube_factory",
            "create-content",
            "--topic",
            "¿Por qué las tapas de alcantarilla son redondas?",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    project_directory = Path(result.stdout.strip())
    assert result.returncode == 0
    assert project_directory.is_dir()
    assert Topic.model_validate_json((project_directory / "topic.json").read_text("utf-8"))
    assert ResearchResult.model_validate_json(
        (project_directory / "research.json").read_text("utf-8")
    )
    assert Script.model_validate_json((project_directory / "script.json").read_text("utf-8"))
    assert ContentManifest.model_validate_json(
        (project_directory / "manifest.json").read_text("utf-8")
    )


def test_create_content_rejects_unsupported_topic(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "youtube_factory",
            "create-content",
            "--topic",
            "Un tema no soportado",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "unsupported topic" in result.stderr
