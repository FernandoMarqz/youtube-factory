"""Tests for the deterministic Phase 2 scene planner."""

from uuid import uuid4

from youtube_factory.adapters.local import (
    LocalResearchProvider,
    LocalScenePlanner,
    LocalScriptGenerator,
)
from youtube_factory.domain.models import Topic


def test_local_scene_planner_creates_a_continuous_eight_scene_timeline() -> None:
    topic = Topic(id=uuid4(), title="¿Por qué las tapas de alcantarilla son redondas?")
    research = LocalResearchProvider().research(topic)
    script = LocalScriptGenerator().generate(topic, research)
    planner = LocalScenePlanner()

    first_plan = planner.plan(script)
    second_plan = planner.plan(script)

    assert len(first_plan.scenes) == 8
    assert first_plan.total_duration_seconds == 34.0
    assert first_plan == second_plan
    assert first_plan.scenes[0].start_seconds == 0.0
    assert first_plan.scenes[-1].end_seconds == first_plan.total_duration_seconds
    assert all(scene.visual_description != scene.narration_segment for scene in first_plan.scenes)
    assert all(scene.visual_intent for scene in first_plan.scenes)
    assert all(scene.visual_description for scene in first_plan.scenes)
