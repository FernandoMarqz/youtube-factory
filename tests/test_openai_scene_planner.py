"""Offline contract and orchestration tests for OpenAI semantic scene planning."""

from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest

from youtube_factory.adapters.local import (
    LocalNarrationGenerator,
    LocalPlaceholderVisualAssetProvider,
)
from youtube_factory.adapters.openai import (
    OpenAIScenePlanner,
    OpenAIScenePlannerConfig,
    OpenAIScenePlanResponse,
)
from youtube_factory.application.config import load_channel_config
from youtube_factory.application.exceptions import ScenePlanningError, ScenePlanValidationError
from youtube_factory.application.services import (
    DeterministicVisualPromptBuilder,
    SceneTimingReconciler,
)
from youtube_factory.domain.enums import HookType
from youtube_factory.domain.models import Script


def arbitrary_script() -> Script:
    """Return a valid non-reference script proving the adapter has no topic fixture."""
    hook = "¿Ves esas juntas?"
    body = "Los puentes se mueven. El acero se expande con el calor."
    ending = "Las juntas evitan daños."
    return Script(
        topic_id=uuid4(),
        hook=hook,
        body=body,
        ending=ending,
        full_narration=f"{hook} {body} {ending}",
        hook_type=HookType.QUESTION,
        estimated_duration_seconds=18.0,
        claims=["Los materiales cambian de dimensión con la temperatura."],
    )


def valid_payload() -> dict[str, object]:
    """Return provider-shaped semantic scenes with exact narration segmentation."""
    return {
        "scenes": [
            {
                "sequence": 1,
                "narration_segment": "¿Ves esas juntas?",
                "visual_description": "Primer plano de una junta entre dos tramos de puente.",
                "visual_intent": "Abrir con un detalle cotidiano que despierte curiosidad.",
                "asset_type": "image",
                "on_screen_text": "¿Por qué están ahí?",
                "transition_suggestion": "quick cut",
                "estimated_duration_seconds": 2.0,
            },
            {
                "sequence": 2,
                "narration_segment": ("Los puentes se mueven. El acero se expande con el calor."),
                "visual_description": (
                    "Diagrama lateral del tablero expandiéndose bajo flechas de temperatura."
                ),
                "visual_intent": "Explicar el movimiento térmico de la estructura.",
                "asset_type": "diagram",
                "on_screen_text": None,
                "transition_suggestion": "push-in",
                "estimated_duration_seconds": 5.0,
            },
            {
                "sequence": 3,
                "narration_segment": "Las juntas evitan daños.",
                "visual_description": (
                    "Dos tramos de puente moviéndose sin chocar gracias al espacio de la junta."
                ),
                "visual_intent": "Cerrar mostrando la función protectora de la junta.",
                "asset_type": "animation",
                "on_screen_text": "Espacio para moverse",
                "transition_suggestion": None,
                "estimated_duration_seconds": 2.0,
            },
        ]
    }


class FakeResponses:
    """SDK-boundary fake recording the structured Responses request."""

    def __init__(self, output: object) -> None:
        self.output = output
        self.kwargs: dict[str, object] = {}

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(output_parsed=self.output)


def planner_config(**overrides: object) -> OpenAIScenePlannerConfig:
    """Return explicit test configuration with small scene-count bounds."""
    values: dict[str, object] = {
        "api_key": "test-key",
        "model": "test-scene-model",
        "language": "es-ES",
        "channel_id": "test-engineering",
        "min_scenes": 3,
        "max_scenes": 4,
        "target_scene_duration_seconds": 4.5,
        "visual_style": "clean educational illustration",
    }
    values.update(overrides)
    return OpenAIScenePlannerConfig(**values)  # type: ignore[arg-type]


def make_planner(
    output: object, **config_overrides: object
) -> tuple[OpenAIScenePlanner, FakeResponses]:
    """Create a planner whose only mocked component is the SDK response boundary."""
    responses = FakeResponses(output)
    client = SimpleNamespace(responses=responses)
    return OpenAIScenePlanner(planner_config(**config_overrides), client=client), responses


def test_structured_request_contains_model_script_and_editorial_constraints() -> None:
    planner, responses = make_planner(valid_payload())
    script = arbitrary_script()

    planner.plan(script)

    assert responses.kwargs["model"] == "test-scene-model"
    assert responses.kwargs["text_format"] is OpenAIScenePlanResponse
    assert script.full_narration in str(responses.kwargs["input"])
    assert script.hook in str(responses.kwargs["input"])
    assert "choose from 3 to 4" in str(responses.kwargs["input"])
    assert "do not paraphrase" in str(responses.kwargs["instructions"])


def test_arbitrary_script_maps_to_continuous_normalized_scene_plan() -> None:
    planner, _ = make_planner(valid_payload())

    plan = planner.plan(arbitrary_script())

    assert len(plan.scenes) == 3
    assert plan.total_duration_seconds == 18.0
    assert plan.scenes[0].start_seconds == 0.0
    assert plan.scenes[-1].end_seconds == 18.0
    assert [scene.duration_seconds for scene in plan.scenes] == [4.0, 10.0, 4.0]
    assert all(
        previous.end_seconds == current.start_seconds
        for previous, current in zip(plan.scenes, plan.scenes[1:], strict=False)
    )


@pytest.mark.parametrize(
    "replacement",
    [
        "Los puentes se mueven.",
        "Los puentes se mueven. El acero se expande con el calor. calor.",
        "Los puentes flotan. El acero se expande con el calor.",
    ],
)
def test_changed_missing_or_duplicated_narration_fails(replacement: str) -> None:
    payload = valid_payload()
    scenes = payload["scenes"]
    assert isinstance(scenes, list)
    scenes[1]["narration_segment"] = replacement
    planner, _ = make_planner(payload)

    with pytest.raises(ScenePlanValidationError, match="reconstruct"):
        planner.plan(arbitrary_script())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("narration_segment", ""),
        ("asset_type", "painting"),
        ("visual_description", ""),
        ("estimated_duration_seconds", 0),
        ("estimated_duration_seconds", -1),
    ],
)
def test_invalid_structured_scene_fields_fail(field: str, value: object) -> None:
    payload = valid_payload()
    scenes = payload["scenes"]
    assert isinstance(scenes, list)
    scenes[0][field] = value
    planner, _ = make_planner(payload)

    with pytest.raises(ScenePlanValidationError, match="schema"):
        planner.plan(arbitrary_script())


def test_invalid_scene_count_fails() -> None:
    payload = valid_payload()
    scenes = payload["scenes"]
    assert isinstance(scenes, list)
    payload["scenes"] = scenes[:2]
    planner, _ = make_planner(payload)

    with pytest.raises(ScenePlanValidationError, match="count"):
        planner.plan(arbitrary_script())


def test_invalid_scene_order_fails() -> None:
    payload = valid_payload()
    scenes = payload["scenes"]
    assert isinstance(scenes, list)
    scenes[1]["sequence"] = 3
    planner, _ = make_planner(payload)

    with pytest.raises(ScenePlanValidationError, match="contiguous"):
        planner.plan(arbitrary_script())


@pytest.mark.parametrize("output", [None, {}, "malformed"])
def test_empty_or_malformed_structured_response_fails(output: object) -> None:
    planner, _ = make_planner(output)

    with pytest.raises(ScenePlanValidationError):
        planner.plan(arbitrary_script())


@pytest.mark.parametrize(
    ("error_name", "message"),
    [
        ("AuthenticationError", "authentication"),
        ("RateLimitError", "rate limit"),
        ("APIConnectionError", "unavailable"),
    ],
)
def test_sdk_errors_are_translated(error_name: str, message: str) -> None:
    error_type = type(error_name, (Exception,), {})

    class FailingResponses:
        def parse(self, **kwargs: object) -> None:
            raise error_type

    planner = OpenAIScenePlanner(
        planner_config(), client=SimpleNamespace(responses=FailingResponses())
    )

    with pytest.raises(ScenePlanningError, match=message):
        planner.plan(arbitrary_script())


def test_missing_api_key_fails_before_client_creation() -> None:
    with pytest.raises(ScenePlanningError, match="OPENAI_API_KEY"):
        OpenAIScenePlanner(planner_config(api_key=""))


def test_ai_plan_remains_compatible_with_timing_and_visual_pipeline() -> None:
    script = arbitrary_script()
    planner, _ = make_planner(valid_payload())
    scene_plan = planner.plan(script)

    generated_narration = LocalNarrationGenerator().generate(script)
    timed_plan = SceneTimingReconciler().reconcile(scene_plan, generated_narration.narration)
    prompt_plan = DeterministicVisualPromptBuilder().build(
        timed_plan, load_channel_config("engineering-es")
    )
    provider = LocalPlaceholderVisualAssetProvider()
    generated_assets = [provider.generate(prompt) for prompt in prompt_plan.prompts]

    assert timed_plan.total_duration_seconds == generated_narration.narration.duration_seconds
    assert timed_plan.scenes[-1].end_seconds == generated_narration.narration.duration_seconds
    assert len(prompt_plan.prompts) == len(scene_plan.scenes)
    assert len(generated_assets) == len(scene_plan.scenes)
    assert all(
        generated.asset.prompt_sha256 == sha256(prompt.prompt.encode("utf-8")).hexdigest()
        for generated, prompt in zip(generated_assets, prompt_plan.prompts, strict=True)
    )
