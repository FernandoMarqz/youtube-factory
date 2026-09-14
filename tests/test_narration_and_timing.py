"""Tests for deterministic WAV narration and media-derived timing reconciliation."""

import wave
from hashlib import sha256
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from youtube_factory.adapters.local import (
    LocalNarrationGenerator,
    LocalResearchProvider,
    LocalScenePlanner,
    LocalScriptGenerator,
)
from youtube_factory.application.services import SceneTimingReconciler
from youtube_factory.domain.models import Narration, ScenePlan, Script, TimedScenePlan, Topic


def reference_script() -> Script:
    """Build the deterministic reference script through its existing providers."""
    topic = Topic(id=uuid4(), title="¿Por qué las tapas de alcantarilla son redondas?")
    research = LocalResearchProvider().research(topic)
    return LocalScriptGenerator().generate(topic, research)


def narration_for_duration(topic_id: UUID, duration_seconds: float) -> Narration:
    """Build valid provider-neutral narration metadata for reconciliation tests."""
    text = "Narración de prueba."
    return Narration(
        topic_id=topic_id,
        file_path="narration.wav",
        duration_seconds=duration_seconds,
        provider="test-narration",
        voice="test-voice",
        sample_rate_hz=16_000,
        narration_text=text,
        script_sha256=sha256(text.encode("utf-8")).hexdigest(),
    )


def test_local_narration_generator_creates_valid_deterministic_wav() -> None:
    script = reference_script()
    generator = LocalNarrationGenerator()

    first = generator.generate(script)
    second = generator.generate(script)

    with wave.open(BytesIO(first.audio_bytes), "rb") as wav_file:
        actual_duration = wav_file.getnframes() / wav_file.getframerate()
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == first.narration.sample_rate_hz

    assert first.audio_bytes == second.audio_bytes
    assert first.narration == second.narration
    assert actual_duration == first.narration.duration_seconds
    assert first.narration.narration_text == script.full_narration


def test_narration_contract_rejects_invalid_duration_and_hash() -> None:
    with pytest.raises(ValidationError):
        Narration(
            topic_id=uuid4(),
            file_path="narration.wav",
            duration_seconds=0,
            provider="test",
            voice="voice",
            sample_rate_hz=16_000,
            narration_text="Texto",
            script_sha256="not-a-hash",
        )


@pytest.mark.parametrize("actual_duration", [36.72, 31.25])
def test_reconciler_scales_timeline_to_actual_narration(actual_duration: float) -> None:
    script = reference_script()
    estimated_plan = LocalScenePlanner().plan(script)
    narration = narration_for_duration(script.topic_id, actual_duration)

    timed_plan = SceneTimingReconciler().reconcile(estimated_plan, narration)

    assert timed_plan.source_total_duration_seconds == 34.0
    assert timed_plan.total_duration_seconds == actual_duration
    assert timed_plan.scenes[0].start_seconds == 0.0
    assert timed_plan.scenes[-1].end_seconds == actual_duration
    assert [scene.sequence for scene in timed_plan.scenes] == list(range(1, 9))
    for previous, current in zip(timed_plan.scenes, timed_plan.scenes[1:], strict=False):
        assert previous.end_seconds == current.start_seconds


def test_timed_scene_plan_requires_narration_duration_alignment() -> None:
    script = reference_script()
    plan = LocalScenePlanner().plan(script)
    timed_plan = SceneTimingReconciler().reconcile(
        plan, narration_for_duration(plan.topic_id, 36.72)
    )

    with pytest.raises(ValidationError, match="narration duration"):
        TimedScenePlan(
            topic_id=plan.topic_id,
            source_total_duration_seconds=34,
            narration_duration_seconds=35,
            total_duration_seconds=36.72,
            reconciliation_strategy="proportional-v1",
            scenes=timed_plan.scenes,
        )


def test_reconciler_rejects_topic_mismatch() -> None:
    plan = ScenePlan.model_validate(LocalScenePlanner().plan(reference_script()))
    narration = narration_for_duration(uuid4(), 36.72)

    with pytest.raises(ValueError, match="same topic"):
        SceneTimingReconciler().reconcile(plan, narration)
