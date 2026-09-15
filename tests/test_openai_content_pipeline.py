"""Offline integration coverage for an arbitrary-topic OpenAI creative pipeline."""

from pathlib import Path
from types import SimpleNamespace

from youtube_factory.adapters.local import (
    FileSystemArtifactStore,
    LocalNarrationGenerator,
    LocalPlaceholderVisualAssetProvider,
)
from youtube_factory.adapters.openai import (
    OpenAIResearchConfig,
    OpenAIResearchProvider,
    OpenAIScenePlanner,
    OpenAIScenePlannerConfig,
    OpenAIScriptConfig,
    OpenAIScriptGenerator,
)
from youtube_factory.application.config import load_channel_config
from youtube_factory.application.services import (
    DeterministicVisualPromptBuilder,
    SceneTimingReconciler,
)
from youtube_factory.application.use_cases import CreateContentUseCase

_TOPIC = "¿Por qué los puentes tienen juntas de dilatación?"
_SOURCE_URL = "https://www.fhwa.dot.gov/bridge/preservation/guide/guide.pdf"


class FakeResponses:
    """One-response SDK boundary fake."""

    def __init__(self, parsed: object, output: object | None = None) -> None:
        self.parsed = parsed
        self.output = [] if output is None else output

    def parse(self, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(output_parsed=self.parsed, output=self.output)


def client(parsed: object, output: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(responses=FakeResponses(parsed, output))


def test_arbitrary_topic_runs_through_mocked_openai_and_local_media(
    tmp_path: Path,
) -> None:
    research_payload = {
        "summary": "Las juntas permiten el movimiento previsto de los puentes.",
        "key_facts": [
            "El acero y el hormigón cambian de dimensión con la temperatura.",
            "Las juntas dejan espacio para movimientos previstos del tablero.",
        ],
        "sources": [
            {
                "title": "Bridge Preservation Guide",
                "url": _SOURCE_URL,
                "publisher": "Federal Highway Administration",
                "notes": "Referencia técnica de conservación de puentes.",
            }
        ],
        "uncertainties": ["La solución concreta depende del diseño del puente."],
    }
    web_output = [
        {
            "type": "web_search_call",
            "action": {
                "sources": [{"url": _SOURCE_URL, "title": "FHWA Bridge Preservation Guide"}]
            },
        }
    ]
    script_payload = {
        "hook": "¿Sabías que un puente se mueve cada día aunque parezca completamente inmóvil?",
        "body": (
            "El acero y el hormigón se expanden cuando sube la temperatura y se contraen cuando "
            "baja. En una estructura larga, esos pequeños cambios se acumulan. Las juntas de "
            "dilatación dejan un espacio controlado para que distintas partes del tablero puedan "
            "desplazarse sin empujarse ni agrietarse. El diseño concreto se adapta al movimiento "
            "previsto y a las condiciones de cada estructura."
        ),
        "ending": (
            "Ese pequeño hueco evita daños grandes: el puente necesita espacio para moverse "
            "con seguridad."
        ),
        "hook_type": "question",
        "supporting_fact_indices": [1, 2],
    }
    scenes_payload = {
        "scenes": [
            {
                "sequence": 1,
                "narration_segment": script_payload["hook"],
                "visual_description": "Primer plano vertical de una junta sobre un puente.",
                "visual_intent": "Plantear la curiosidad visual.",
                "asset_type": "image",
                "on_screen_text": "Los puentes se mueven",
                "transition_suggestion": "quick cut",
                "estimated_duration_seconds": 3.0,
            },
            {
                "sequence": 2,
                "narration_segment": script_payload["body"],
                "visual_description": "Diagrama del tablero expandiéndose con la temperatura.",
                "visual_intent": "Explicar el movimiento y la función de la junta.",
                "asset_type": "diagram",
                "on_screen_text": None,
                "transition_suggestion": "push-in",
                "estimated_duration_seconds": 8.0,
            },
            {
                "sequence": 3,
                "narration_segment": script_payload["ending"],
                "visual_description": "Junta abriéndose sin dañar los dos tramos del tablero.",
                "visual_intent": "Mostrar el beneficio práctico como cierre.",
                "asset_type": "animation",
                "on_screen_text": "Espacio para moverse",
                "transition_suggestion": None,
                "estimated_duration_seconds": 3.0,
            },
        ]
    }
    channel = load_channel_config("engineering-es")
    research_provider = OpenAIResearchProvider(
        OpenAIResearchConfig("test-key", "research-model", "es-ES", channel.id, 5),
        client=client(research_payload, web_output),
    )
    script_generator = OpenAIScriptGenerator(
        OpenAIScriptConfig(
            "test-key",
            "script-model",
            "es-ES",
            channel.id,
            channel.content.niche,
            channel.content.target_duration_seconds,
            channel.content.min_duration_seconds,
            channel.content.max_duration_seconds,
        ),
        client=client(script_payload),
    )
    scene_planner = OpenAIScenePlanner(
        OpenAIScenePlannerConfig(
            "test-key",
            "scene-model",
            "es-ES",
            channel.id,
            3,
            4,
            4.5,
            channel.visuals.style,
        ),
        client=client(scenes_payload),
    )
    use_case = CreateContentUseCase(
        research_provider,
        script_generator,
        scene_planner,
        LocalNarrationGenerator(),
        SceneTimingReconciler(),
        FileSystemArtifactStore(tmp_path),
        channel,
        DeterministicVisualPromptBuilder(),
        LocalPlaceholderVisualAssetProvider(),
    )

    result = use_case.execute(_TOPIC)

    assert result.topic.title == _TOPIC
    assert result.research.sources[0].publisher == "Federal Highway Administration"
    assert result.script.topic_id == result.topic.id
    assert result.scene_plan.topic_id == result.topic.id
    assert result.timed_scene_plan.total_duration_seconds == result.narration.duration_seconds
    assert len(result.visual_asset_manifest.assets) == 3
    assert result.manifest.research_provider.provider == "openai"
    assert result.manifest.script_generator.provider == "openai"
    assert result.manifest.scene_planner is not None
    assert result.manifest.scene_planner.provider == "openai"
    assert (result.project_directory / "research.json").is_file()
    assert (result.project_directory / "script.json").is_file()
    assert (result.project_directory / "visual-assets.json").is_file()
