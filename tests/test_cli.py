"""Tests for the bootstrap CLI."""

import os
import subprocess
import sys
from pathlib import Path

from pytest import MonkeyPatch

from youtube_factory.adapters.local import LocalPlaceholderVisualAssetProvider, LocalScenePlanner
from youtube_factory.adapters.openai import OpenAIScenePlanner
from youtube_factory.application.config import load_channel_config
from youtube_factory.cli.main import build_scene_planner, build_visual_asset_provider
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
            "--channel",
            "engineering-es",
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
    visual_prompts = VisualPromptPlan.model_validate_json(
        (project_directory / "visual-prompts.json").read_text("utf-8")
    )
    visual_assets = VisualAssetManifest.model_validate_json(
        (project_directory / "visual-assets.json").read_text("utf-8")
    )
    assert len(visual_prompts.prompts) == len(timed_scene_plan.scenes)
    assert len(visual_assets.assets) == len(timed_scene_plan.scenes)
    assert all((project_directory / asset.file_path).is_file() for asset in visual_assets.assets)
    assert timed_scene_plan.total_duration_seconds == narration.duration_seconds
    manifest = ContentManifest.model_validate_json(
        (project_directory / "manifest.json").read_text("utf-8")
    )
    assert manifest.channel_id == "engineering-es"
    assert manifest.pipeline_version == "content-pipeline-v1"
    assert manifest.narration_generator is not None
    assert manifest.narration_generator.provider == "local"
    assert manifest.narration_generator.duration_seconds == narration.duration_seconds
    assert manifest.scene_planner is not None
    assert manifest.scene_planner.provider == "local"
    assert manifest.scene_planner.model is None
    assert manifest.scene_planner.identifier == "local-scene-planner-v1"
    assert manifest.visual_asset_generator is not None
    assert manifest.visual_asset_generator.provider == "local-placeholder"
    assert manifest.visual_asset_generator.asset_count == len(timed_scene_plan.scenes)


def test_openai_visual_override_fails_cleanly_without_api_key(tmp_path: Path) -> None:
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
            "local",
            "--visual-provider",
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
    assert "OPENAI_API_KEY is required when visual provider is openai" in result.stderr


def test_explicit_local_visual_override_wins_without_openai_key(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    channel = load_channel_config("engineering-es")

    provider = build_visual_asset_provider(channel, "local-placeholder")

    assert isinstance(provider, LocalPlaceholderVisualAssetProvider)


def test_scene_planner_defaults_to_channel_local_without_openai_key(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    channel = load_channel_config("engineering-es")

    assert isinstance(build_scene_planner(channel), LocalScenePlanner)
    assert isinstance(build_scene_planner(channel, "local"), LocalScenePlanner)


def test_openai_scene_planner_override_uses_channel_model(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    channel = load_channel_config("engineering-es")

    planner = build_scene_planner(channel, "openai")

    assert isinstance(planner, OpenAIScenePlanner)
    assert planner.model == "gpt-5.6-luna"


def test_openai_scene_planner_override_fails_cleanly_without_key(tmp_path: Path) -> None:
    environment = {**os.environ, "OPENAI_API_KEY": ""}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "youtube_factory",
            "create-content",
            "--topic",
            "¿Por qué las tapas de alcantarilla son redondas?",
            "--scene-planner",
            "openai",
            "--narration-provider",
            "local",
            "--visual-provider",
            "local-placeholder",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode != 0
    assert "OPENAI_API_KEY is required when scene planner is openai" in result.stderr


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
