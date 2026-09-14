"""Tests for initial domain contracts."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from youtube_factory.domain.enums import AssetSourceType, AssetType
from youtube_factory.domain.models import Asset, RenderResult, Scene, ScenePlan, ShortProject, Topic


def test_topic_has_spanish_defaults_and_is_immutable() -> None:
    topic = Topic(title="Por que las tapas de alcantarilla son redondas")

    assert topic.language == "es"
    assert topic.category == "engineering_curiosities"
    with pytest.raises(ValidationError):
        topic.title = "Otro tema"


def test_scene_plan_requires_contiguous_sequences() -> None:
    with pytest.raises(ValidationError, match="contiguous"):
        ScenePlan(
            topic_id=uuid4(),
            scenes=[
                Scene(
                    sequence=1,
                    narration_segment="Primera escena",
                    start_seconds=0,
                    end_seconds=2,
                    visual_description="Una tapa circular",
                    visual_intent="Introducir el tema",
                    duration_seconds=2,
                    asset_type=AssetType.IMAGE,
                ),
                Scene(
                    sequence=3,
                    narration_segment="Tercera escena",
                    start_seconds=2,
                    end_seconds=4,
                    visual_description="Una alcantarilla",
                    visual_intent="Explicar la geometría",
                    duration_seconds=2,
                    asset_type=AssetType.IMAGE,
                ),
            ],
            total_duration_seconds=4,
        )


def test_short_project_rejects_artifact_from_another_topic() -> None:
    topic = Topic(title="Tema")
    asset = Asset(
        topic_id=uuid4(),
        scene_sequence=1,
        file_path="assets/scene_01.png",
        asset_type=AssetType.IMAGE,
        source_type=AssetSourceType.LOCAL,
    )

    with pytest.raises(ValidationError, match="assets must belong"):
        ShortProject(topic=topic, working_directory="output/short_000001", assets=[asset])


def test_render_result_requires_vertical_output() -> None:
    with pytest.raises(ValidationError, match="vertical"):
        RenderResult(
            job_id=uuid4(),
            output_path="final.mp4",
            width=1920,
            height=1080,
            duration_seconds=30,
            fps=30,
        )
