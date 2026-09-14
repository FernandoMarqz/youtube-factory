"""Tests for Topic -> ResearchResult -> Script application orchestration."""

from pathlib import Path

import pytest

from youtube_factory.adapters.local import (
    LocalNarrationGenerator,
    LocalResearchProvider,
    LocalScenePlanner,
    LocalScriptGenerator,
)
from youtube_factory.application.exceptions import UnsupportedTopicError
from youtube_factory.application.services import SceneTimingReconciler
from youtube_factory.application.use_cases import CreateContentUseCase
from youtube_factory.domain.models import ResearchResult, ScenePlan, Script, Topic
from youtube_factory.ports import GeneratedNarration


class RecordingResearchProvider:
    """Port test double that records the supplied topic."""

    identifier = "recording-research"

    def __init__(self) -> None:
        self.invocations: list[Topic] = []
        self._delegate = LocalResearchProvider()

    def research(self, topic: Topic) -> ResearchResult:
        self.invocations.append(topic)
        return self._delegate.research(topic)


class RecordingScriptGenerator:
    """Port test double that records the supplied domain values."""

    identifier = "recording-script"

    def __init__(self) -> None:
        self.invocations: list[tuple[Topic, ResearchResult]] = []
        self._delegate = LocalScriptGenerator()

    def generate(self, topic: Topic, research: ResearchResult) -> Script:
        self.invocations.append((topic, research))
        return self._delegate.generate(topic, research)


class RecordingScenePlanner:
    """Port test double that records the supplied script."""

    identifier = "recording-scene-planner"

    def __init__(self) -> None:
        self.invocations: list[Script] = []
        self._delegate = LocalScenePlanner()

    def plan(self, script: Script) -> ScenePlan:
        self.invocations.append(script)
        return self._delegate.plan(script)


class RecordingArtifactStore:
    """Minimal artifact-store port test double."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.invocations = 0

    def save(self, project_id: str, *args: object) -> Path:
        self.invocations += 1
        return self.root / project_id


class RecordingNarrationGenerator:
    """Port test double that records the final script passed to narration."""

    identifier = "recording-narration"

    def __init__(self) -> None:
        self.invocations: list[Script] = []
        self._delegate = LocalNarrationGenerator()

    def generate(self, script: Script) -> GeneratedNarration:
        self.invocations.append(script)
        return self._delegate.generate(script)


class FailingResearchProvider:
    """Research port that models an unsupported deterministic topic."""

    identifier = "failing-research"

    def research(self, topic: Topic) -> ResearchResult:
        raise UnsupportedTopicError("research is unavailable")


class FailingScriptGenerator:
    """Script port that models an unsupported deterministic topic."""

    identifier = "failing-script"

    def generate(self, topic: Topic, research: ResearchResult) -> Script:
        raise UnsupportedTopicError("script generation is unavailable")


class FailingScenePlanner:
    """Scene-planning port that models a local planning failure."""

    identifier = "failing-scene-planner"

    def plan(self, script: Script) -> ScenePlan:
        raise UnsupportedTopicError("scene planning is unavailable")


class FailingNarrationGenerator:
    """Narration port that models an unavailable local generator."""

    identifier = "failing-narration"

    def generate(self, script: Script) -> GeneratedNarration:
        raise UnsupportedTopicError("narration generation is unavailable")


def test_use_case_orchestrates_through_ports(tmp_path: Path) -> None:
    research_provider = RecordingResearchProvider()
    script_generator = RecordingScriptGenerator()
    scene_planner = RecordingScenePlanner()
    narration_generator = RecordingNarrationGenerator()
    artifact_store = RecordingArtifactStore(tmp_path)
    use_case = CreateContentUseCase(
        research_provider,
        script_generator,
        scene_planner,
        narration_generator,
        SceneTimingReconciler(),
        artifact_store,
    )

    result = use_case.execute("¿Por qué las tapas de alcantarilla son redondas?")

    assert len(research_provider.invocations) == 1
    assert len(script_generator.invocations) == 1
    assert len(scene_planner.invocations) == 1
    assert len(narration_generator.invocations) == 1
    assert artifact_store.invocations == 1
    assert result.research.topic_id == result.topic.id
    assert result.script.topic_id == result.topic.id
    assert result.scene_plan.topic_id == result.topic.id
    assert result.timed_scene_plan.narration_duration_seconds == result.narration.duration_seconds
    assert result.project_directory == tmp_path / str(result.project_id)


def test_use_case_propagates_research_provider_failure(tmp_path: Path) -> None:
    use_case = CreateContentUseCase(
        FailingResearchProvider(),
        LocalScriptGenerator(),
        LocalScenePlanner(),
        LocalNarrationGenerator(),
        SceneTimingReconciler(),
        RecordingArtifactStore(tmp_path),
    )

    with pytest.raises(UnsupportedTopicError, match="research is unavailable"):
        use_case.execute("¿Por qué las tapas de alcantarilla son redondas?")


def test_use_case_propagates_script_provider_failure(tmp_path: Path) -> None:
    use_case = CreateContentUseCase(
        LocalResearchProvider(),
        FailingScriptGenerator(),
        LocalScenePlanner(),
        LocalNarrationGenerator(),
        SceneTimingReconciler(),
        RecordingArtifactStore(tmp_path),
    )

    with pytest.raises(UnsupportedTopicError, match="script generation is unavailable"):
        use_case.execute("¿Por qué las tapas de alcantarilla son redondas?")


def test_use_case_does_not_persist_a_partial_pipeline_when_planning_fails(tmp_path: Path) -> None:
    artifact_store = RecordingArtifactStore(tmp_path)
    use_case = CreateContentUseCase(
        LocalResearchProvider(),
        LocalScriptGenerator(),
        FailingScenePlanner(),
        LocalNarrationGenerator(),
        SceneTimingReconciler(),
        artifact_store,
    )

    with pytest.raises(UnsupportedTopicError, match="scene planning is unavailable"):
        use_case.execute("¿Por qué las tapas de alcantarilla son redondas?")

    assert artifact_store.invocations == 0


def test_use_case_does_not_persist_when_narration_generation_fails(tmp_path: Path) -> None:
    artifact_store = RecordingArtifactStore(tmp_path)
    use_case = CreateContentUseCase(
        LocalResearchProvider(),
        LocalScriptGenerator(),
        LocalScenePlanner(),
        FailingNarrationGenerator(),
        SceneTimingReconciler(),
        artifact_store,
    )

    with pytest.raises(UnsupportedTopicError, match="narration generation is unavailable"):
        use_case.execute("¿Por qué las tapas de alcantarilla son redondas?")

    assert artifact_store.invocations == 0
