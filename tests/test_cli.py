"""Tests for the bootstrap CLI."""

import os
import subprocess
import sys
from pathlib import Path

from youtube_factory.domain.models import (
    ContentManifest,
    Narration,
    ResearchResult,
    ScenePlan,
    Script,
    TimedScenePlan,
    Topic,
)


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
            "--narration-provider",
            "local",
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
    assert ScenePlan.model_validate_json((project_directory / "scenes.json").read_text("utf-8"))
    narration = Narration.model_validate_json(
        (project_directory / "narration.json").read_text("utf-8")
    )
    timed_scene_plan = TimedScenePlan.model_validate_json(
        (project_directory / "timed-scenes.json").read_text("utf-8")
    )
    assert ContentManifest.model_validate_json(
        (project_directory / "manifest.json").read_text("utf-8")
    )
    assert (project_directory / "narration.wav").is_file()
    assert timed_scene_plan.total_duration_seconds == narration.duration_seconds


def test_openai_provider_fails_cleanly_without_api_key(tmp_path: Path) -> None:
    environment = {**os.environ, "OPENAI_API_KEY": ""}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "youtube_factory",
            "create-content",
            "--topic",
            "¿Por qué las tapas de alcantarilla son redondas?",
            "--narration-provider",
            "openai",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode != 0
    assert "OPENAI_API_KEY is required" in result.stderr


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
