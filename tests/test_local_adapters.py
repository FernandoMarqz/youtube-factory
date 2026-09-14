"""Tests for deterministic local adapters and artifact persistence."""

from pathlib import Path
from uuid import uuid4

from youtube_factory.adapters.local import (
    FileSystemArtifactStore,
    LocalNarrationGenerator,
    LocalResearchProvider,
    LocalScenePlanner,
    LocalScriptGenerator,
)
from youtube_factory.application.services import SceneTimingReconciler
from youtube_factory.application.use_cases import CreateContentUseCase
from youtube_factory.domain.models import (
    ContentManifest,
    Narration,
    ResearchResult,
    ScenePlan,
    Script,
    TimedScenePlan,
    Topic,
)


def test_local_providers_are_deterministic_for_the_reference_topic() -> None:
    topic = Topic(id=uuid4(), title="¿Por qué las tapas de alcantarilla son redondas?")
    research_provider = LocalResearchProvider()
    script_generator = LocalScriptGenerator()

    first_research = research_provider.research(topic)
    second_research = research_provider.research(topic)
    first_script = script_generator.generate(topic, first_research)
    second_script = script_generator.generate(topic, second_research)

    assert first_research == second_research
    assert first_script == second_script


def test_file_system_store_writes_parseable_domain_models(tmp_path: Path) -> None:
    use_case = CreateContentUseCase(
        LocalResearchProvider(),
        LocalScriptGenerator(),
        LocalScenePlanner(),
        LocalNarrationGenerator(),
        SceneTimingReconciler(),
        FileSystemArtifactStore(tmp_path),
    )
    result = use_case.execute("¿Por qué las tapas de alcantarilla son redondas?")

    topic = Topic.model_validate_json((result.project_directory / "topic.json").read_text("utf-8"))
    research = ResearchResult.model_validate_json(
        (result.project_directory / "research.json").read_text("utf-8")
    )
    script = Script.model_validate_json(
        (result.project_directory / "script.json").read_text("utf-8")
    )
    scene_plan = ScenePlan.model_validate_json(
        (result.project_directory / "scenes.json").read_text("utf-8")
    )
    narration = Narration.model_validate_json(
        (result.project_directory / "narration.json").read_text("utf-8")
    )
    timed_scene_plan = TimedScenePlan.model_validate_json(
        (result.project_directory / "timed-scenes.json").read_text("utf-8")
    )
    manifest = ContentManifest.model_validate_json(
        (result.project_directory / "manifest.json").read_text("utf-8")
    )

    assert topic == result.topic
    assert research == result.research
    assert script == result.script
    assert scene_plan == result.scene_plan
    assert narration == result.narration
    assert timed_scene_plan == result.timed_scene_plan
    assert (result.project_directory / "narration.wav").is_file()
    assert manifest == result.manifest

    first_script_json = (result.project_directory / "script.json").read_text("utf-8")
    repeated_result = use_case.execute("¿Por qué las tapas de alcantarilla son redondas?")
    assert repeated_result.project_directory == result.project_directory
    assert (repeated_result.project_directory / "script.json").read_text(
        "utf-8"
    ) == first_script_json
