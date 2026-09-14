"""Tests for Topic -> ResearchResult -> Script application orchestration."""

from pathlib import Path

import pytest

from youtube_factory.adapters.local import LocalResearchProvider, LocalScriptGenerator
from youtube_factory.application.exceptions import UnsupportedTopicError
from youtube_factory.application.use_cases import CreateContentUseCase
from youtube_factory.domain.models import ResearchResult, Script, Topic


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


class RecordingArtifactStore:
    """Minimal artifact-store port test double."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.invocations = 0

    def save(self, project_id: str, *args: object) -> Path:
        self.invocations += 1
        return self.root / project_id


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


def test_use_case_orchestrates_through_ports(tmp_path: Path) -> None:
    research_provider = RecordingResearchProvider()
    script_generator = RecordingScriptGenerator()
    artifact_store = RecordingArtifactStore(tmp_path)
    use_case = CreateContentUseCase(research_provider, script_generator, artifact_store)

    result = use_case.execute("¿Por qué las tapas de alcantarilla son redondas?")

    assert len(research_provider.invocations) == 1
    assert len(script_generator.invocations) == 1
    assert artifact_store.invocations == 1
    assert result.research.topic_id == result.topic.id
    assert result.script.topic_id == result.topic.id
    assert result.project_directory == tmp_path / str(result.project_id)


def test_use_case_propagates_research_provider_failure(tmp_path: Path) -> None:
    use_case = CreateContentUseCase(
        FailingResearchProvider(), LocalScriptGenerator(), RecordingArtifactStore(tmp_path)
    )

    with pytest.raises(UnsupportedTopicError, match="research is unavailable"):
        use_case.execute("¿Por qué las tapas de alcantarilla son redondas?")


def test_use_case_propagates_script_provider_failure(tmp_path: Path) -> None:
    use_case = CreateContentUseCase(
        LocalResearchProvider(), FailingScriptGenerator(), RecordingArtifactStore(tmp_path)
    )

    with pytest.raises(UnsupportedTopicError, match="script generation is unavailable"):
        use_case.execute("¿Por qué las tapas de alcantarilla son redondas?")
