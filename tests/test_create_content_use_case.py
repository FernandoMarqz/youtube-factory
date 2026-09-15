"""Tests for Topic -> ResearchResult -> Script application orchestration."""

from pathlib import Path

import pytest

from youtube_factory.adapters.local import (
    LocalNarrationGenerator,
    LocalPlaceholderVisualAssetProvider,
    LocalResearchProvider,
    LocalScenePlanner,
    LocalScriptGenerator,
)
from youtube_factory.application.config import ChannelConfig, load_channel_config
from youtube_factory.application.exceptions import UnsupportedTopicError, VisualAssetGenerationError
from youtube_factory.application.services import (
    DeterministicVisualPromptBuilder,
    SceneTimingReconciler,
)
from youtube_factory.application.use_cases import CreateContentUseCase
from youtube_factory.domain.models import (
    ResearchResult,
    ScenePlan,
    Script,
    TimedScenePlan,
    Topic,
    VisualPrompt,
    VisualPromptPlan,
)
from youtube_factory.ports import GeneratedNarration, GeneratedVisualAsset


def visual_dependencies() -> tuple[
    ChannelConfig, DeterministicVisualPromptBuilder, LocalPlaceholderVisualAssetProvider
]:
    """Return the explicit offline visual composition used by application tests."""
    return (
        load_channel_config("engineering-es"),
        DeterministicVisualPromptBuilder(),
        LocalPlaceholderVisualAssetProvider(),
    )


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


class RecordingVisualPromptBuilder:
    """Application-service double proving the timed plan crosses the prompt boundary."""

    identifier = "recording-visual-prompts"

    def __init__(self) -> None:
        self.invocations: list[TimedScenePlan] = []
        self._delegate = DeterministicVisualPromptBuilder()

    def build(
        self, timed_scene_plan: TimedScenePlan, channel_config: ChannelConfig
    ) -> VisualPromptPlan:
        self.invocations.append(timed_scene_plan)
        return self._delegate.build(timed_scene_plan, channel_config)


class RecordingVisualAssetProvider:
    """Visual provider double proving every prompt is generated through the port."""

    identifier = "local-placeholder"
    model: str | None = None

    def __init__(self) -> None:
        self.invocations: list[VisualPrompt] = []
        self._delegate = LocalPlaceholderVisualAssetProvider()

    def generate(self, prompt: VisualPrompt) -> GeneratedVisualAsset:
        self.invocations.append(prompt)
        return self._delegate.generate(prompt)


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


class FailingVisualAssetProvider:
    """Visual provider that models an unavailable image service."""

    identifier = "failing-visual"
    model: str | None = None

    def generate(self, prompt: VisualPrompt) -> GeneratedVisualAsset:
        raise RuntimeError("image service unavailable")


def test_use_case_orchestrates_through_ports(tmp_path: Path) -> None:
    research_provider = RecordingResearchProvider()
    script_generator = RecordingScriptGenerator()
    scene_planner = RecordingScenePlanner()
    narration_generator = RecordingNarrationGenerator()
    visual_prompt_builder = RecordingVisualPromptBuilder()
    visual_asset_provider = RecordingVisualAssetProvider()
    artifact_store = RecordingArtifactStore(tmp_path)
    use_case = CreateContentUseCase(
        research_provider,
        script_generator,
        scene_planner,
        narration_generator,
        SceneTimingReconciler(),
        artifact_store,
        load_channel_config("engineering-es"),
        visual_prompt_builder,
        visual_asset_provider,
    )

    result = use_case.execute("¿Por qué las tapas de alcantarilla son redondas?")

    assert len(research_provider.invocations) == 1
    assert len(script_generator.invocations) == 1
    assert len(scene_planner.invocations) == 1
    assert len(narration_generator.invocations) == 1
    assert len(visual_prompt_builder.invocations) == 1
    assert len(visual_asset_provider.invocations) == len(result.timed_scene_plan.scenes)
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
        *visual_dependencies(),
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
        *visual_dependencies(),
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
        *visual_dependencies(),
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
        *visual_dependencies(),
    )

    with pytest.raises(UnsupportedTopicError, match="narration generation is unavailable"):
        use_case.execute("¿Por qué las tapas de alcantarilla son redondas?")

    assert artifact_store.invocations == 0


def test_use_case_translates_visual_failure_and_does_not_persist(tmp_path: Path) -> None:
    artifact_store = RecordingArtifactStore(tmp_path)
    use_case = CreateContentUseCase(
        LocalResearchProvider(),
        LocalScriptGenerator(),
        LocalScenePlanner(),
        LocalNarrationGenerator(),
        SceneTimingReconciler(),
        artifact_store,
        load_channel_config("engineering-es"),
        DeterministicVisualPromptBuilder(),
        FailingVisualAssetProvider(),
    )

    with pytest.raises(VisualAssetGenerationError, match="scene 1"):
        use_case.execute("¿Por qué las tapas de alcantarilla son redondas?")

    assert artifact_store.invocations == 0
