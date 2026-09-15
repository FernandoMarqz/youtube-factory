"""Offline tests for OpenAI scripts grounded in persisted research."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import HttpUrl

from youtube_factory.adapters.openai import (
    OpenAIScriptConfig,
    OpenAIScriptGenerator,
    OpenAIScriptResponse,
)
from youtube_factory.application.exceptions import ScriptGenerationError, ScriptValidationError
from youtube_factory.application.services import estimate_spoken_duration_seconds
from youtube_factory.domain.models import ResearchResult, Source, Topic


def topic_and_research() -> tuple[Topic, ResearchResult]:
    topic = Topic(id=uuid4(), title="¿Por qué los puentes tienen juntas de dilatación?")
    research = ResearchResult(
        topic_id=topic.id,
        summary="Los puentes incorporan juntas para admitir movimientos previstos.",
        key_facts=[
            "El acero y el hormigón cambian de dimensión con la temperatura.",
            "Las juntas dejan espacio para movimientos previstos del tablero.",
            "El diseño de cada junta depende de las cargas y del entorno.",
        ],
        sources=[
            Source(
                title="Bridge Preservation Guide",
                url=HttpUrl("https://www.fhwa.dot.gov/bridge/preservation/guide/guide.pdf"),
                publisher="Federal Highway Administration",
                retrieved_at=datetime.now(UTC),
            )
        ],
        uncertainties=["La solución concreta varía entre puentes."],
    )
    return topic, research


def script_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "hook": "¿Sabías que un puente se mueve cada día aunque parezca completamente inmóvil?",
        "body": (
            "El acero y el hormigón se expanden cuando sube la temperatura y se contraen cuando "
            "baja. En una estructura larga, esos pequeños cambios se acumulan. Las juntas de "
            "dilatación dejan un espacio controlado para que distintas partes del tablero puedan "
            "desplazarse sin empujarse ni agrietarse. Su diseño concreto depende de las cargas, "
            "el tamaño del puente y las condiciones del entorno."
        ),
        "ending": (
            "Ese pequeño hueco evita daños grandes: el puente necesita espacio para moverse "
            "con seguridad."
        ),
        "hook_type": "question",
        "supporting_fact_indices": [1, 2, 3],
    }
    payload.update(overrides)
    return payload


class FakeResponses:
    def __init__(self, parsed: object) -> None:
        self.parsed = parsed
        self.kwargs: dict[str, object] = {}

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(output_parsed=self.parsed)


def config(**overrides: object) -> OpenAIScriptConfig:
    values: dict[str, object] = {
        "api_key": "test-key",
        "model": "test-script-model",
        "language": "es-ES",
        "channel_id": "engineering-test",
        "niche": "engineering_curiosities",
        "target_duration_seconds": 35,
        "min_duration_seconds": 25,
        "max_duration_seconds": 45,
    }
    values.update(overrides)
    return OpenAIScriptConfig(**values)  # type: ignore[arg-type]


def make_generator(
    parsed: object, **config_overrides: object
) -> tuple[OpenAIScriptGenerator, FakeResponses]:
    responses = FakeResponses(parsed)
    client = SimpleNamespace(responses=responses)
    return OpenAIScriptGenerator(config(**config_overrides), client=client), responses


def test_request_uses_model_topic_research_and_structured_schema() -> None:
    generator, responses = make_generator(script_payload())
    topic, research = topic_and_research()

    generator.generate(topic, research)

    assert responses.kwargs["model"] == "test-script-model"
    assert responses.kwargs["text_format"] is OpenAIScriptResponse
    request = str(responses.kwargs["input"])
    assert topic.title in request
    assert research.summary in request
    assert all(fact in request for fact in research.key_facts)
    assert "Use only the supplied" in str(responses.kwargs["instructions"])
    assert "tools" not in responses.kwargs


def test_arbitrary_topic_maps_to_consistent_grounded_script() -> None:
    generator, _ = make_generator(script_payload())
    topic, research = topic_and_research()

    script = generator.generate(topic, research)

    assert script.topic_id == topic.id
    assert script.full_narration == f"{script.hook} {script.body} {script.ending}"
    assert script.estimated_duration_seconds == estimate_spoken_duration_seconds(
        script.full_narration
    )
    assert script.claims == research.key_facts
    assert 25 <= script.estimated_duration_seconds <= 45


@pytest.mark.parametrize(
    "payload",
    [
        script_payload(hook=""),
        script_payload(ending=""),
        script_payload(body=""),
        script_payload(hook_type="unsupported"),
        script_payload(supporting_fact_indices=[]),
        None,
        {},
    ],
)
def test_empty_or_malformed_script_is_rejected(payload: object) -> None:
    generator, _ = make_generator(payload)
    topic, research = topic_and_research()

    with pytest.raises(ScriptValidationError):
        generator.generate(topic, research)


@pytest.mark.parametrize("indices", [[1, 1], [4]])
def test_duplicate_or_unknown_grounding_indices_are_rejected(indices: list[int]) -> None:
    generator, _ = make_generator(script_payload(supporting_fact_indices=indices))
    topic, research = topic_and_research()

    with pytest.raises(ScriptValidationError):
        generator.generate(topic, research)


def test_script_outside_duration_bounds_is_rejected() -> None:
    generator, _ = make_generator(script_payload(hook="Breve.", body="Muy breve.", ending="Fin."))
    topic, research = topic_and_research()

    with pytest.raises(ScriptValidationError, match="duration"):
        generator.generate(topic, research)


def test_research_must_belong_to_topic() -> None:
    generator, responses = make_generator(script_payload())
    topic, research = topic_and_research()
    other_topic = Topic(title="Otro tema")

    with pytest.raises(ScriptValidationError, match="does not belong"):
        generator.generate(other_topic, research)

    assert responses.kwargs == {}


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

    generator = OpenAIScriptGenerator(
        config(), client=SimpleNamespace(responses=FailingResponses())
    )
    topic, research = topic_and_research()

    with pytest.raises(ScriptGenerationError, match=message):
        generator.generate(topic, research)


def test_missing_key_fails_before_client_creation() -> None:
    with pytest.raises(ScriptGenerationError, match="OPENAI_API_KEY"):
        OpenAIScriptGenerator(config(api_key=""))
