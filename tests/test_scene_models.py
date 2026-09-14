"""Tests for the timed audiovisual ScenePlan contracts."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from youtube_factory.domain.enums import AssetType
from youtube_factory.domain.models import Scene, ScenePlan


def make_scene(sequence: int, start: float, end: float) -> Scene:
    """Build a valid scene with timing derived from its boundaries."""
    return Scene(
        sequence=sequence,
        narration_segment=f"Narración {sequence}",
        start_seconds=start,
        end_seconds=end,
        duration_seconds=end - start,
        visual_description=f"Visual específico {sequence}",
        visual_intent=f"Propósito visual {sequence}",
        asset_type=AssetType.DIAGRAM,
    )


def test_scene_and_scene_plan_accept_a_continuous_timeline() -> None:
    plan = ScenePlan(
        topic_id=uuid4(),
        scenes=[make_scene(1, 0, 3), make_scene(2, 3, 6)],
        total_duration_seconds=6,
    )

    assert plan.scenes[0].start_seconds == 0
    assert plan.total_duration_seconds == 6


def test_scene_rejects_an_invalid_end_or_duration() -> None:
    with pytest.raises(ValidationError, match="end time"):
        Scene(
            sequence=1,
            narration_segment="Narración",
            start_seconds=3,
            end_seconds=2,
            duration_seconds=1,
            visual_description="Diagrama",
            visual_intent="Explicar",
            asset_type=AssetType.DIAGRAM,
        )

    with pytest.raises(ValidationError, match="duration"):
        Scene(
            sequence=1,
            narration_segment="Narración",
            start_seconds=0,
            end_seconds=3,
            duration_seconds=2,
            visual_description="Diagrama",
            visual_intent="Explicar",
            asset_type=AssetType.DIAGRAM,
        )


def test_scene_plan_rejects_overlaps_and_gaps() -> None:
    with pytest.raises(ValidationError, match="gaps or overlaps"):
        ScenePlan(
            topic_id=uuid4(),
            scenes=[make_scene(1, 0, 3), make_scene(2, 2.5, 6)],
            total_duration_seconds=6,
        )

    with pytest.raises(ValidationError, match="gaps or overlaps"):
        ScenePlan(
            topic_id=uuid4(),
            scenes=[make_scene(1, 0, 3), make_scene(2, 4, 6)],
            total_duration_seconds=6,
        )


def test_scene_plan_rejects_out_of_order_sequences_and_total_duration() -> None:
    with pytest.raises(ValidationError, match="contiguous"):
        ScenePlan(
            topic_id=uuid4(),
            scenes=[make_scene(2, 0, 3)],
            total_duration_seconds=3,
        )

    with pytest.raises(ValidationError, match="total duration"):
        ScenePlan(
            topic_id=uuid4(),
            scenes=[make_scene(1, 0, 3)],
            total_duration_seconds=4,
        )
