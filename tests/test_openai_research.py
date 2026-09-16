"""Offline tests for source-backed OpenAI research."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from youtube_factory.adapters.openai import (
    OpenAIResearchConfig,
    OpenAIResearchProvider,
    OpenAIResearchResponse,
)
from youtube_factory.application.exceptions import ResearchError, ResearchValidationError
from youtube_factory.domain.models import Topic

_SOURCE_URL = "https://www.fhwa.dot.gov/bridge/preservation/guide/guide.pdf"


def research_payload(**overrides: object) -> dict[str, object]:
    """Return a valid provider-shaped research response."""
    payload: dict[str, object] = {
        "summary": "Las juntas permiten movimientos previstos del tablero del puente.",
        "key_facts": [
            "Los materiales del puente cambian de dimensión con la temperatura.",
            "Las juntas proporcionan espacio para movimientos previstos por el diseño.",
        ],
        "sources": [
            {
                "title": "Bridge Preservation Guide",
                "url": _SOURCE_URL,
                "publisher": "Federal Highway Administration",
                "notes": "Describe conservación y componentes de puentes.",
            }
        ],
        "uncertainties": ["El tipo y el recorrido de una junta dependen del diseño y del entorno."],
    }
    payload.update(overrides)
    return payload


def web_output(url: str = _SOURCE_URL) -> list[dict[str, object]]:
    """Model the source evidence returned by the Responses web-search tool."""
    return [
        {
            "type": "web_search_call",
            "action": {
                "sources": [
                    {
                        "type": "url",
                        "url": url,
                        "title": "FHWA Bridge Preservation Guide",
                    }
                ]
            },
        }
    ]


class FakeResponses:
    """SDK boundary fake recording a Responses API structured request."""

    def __init__(self, parsed: object, output: object | None = None) -> None:
        self.parsed = parsed
        self.output = web_output() if output is None else output
        self.kwargs: dict[str, object] = {}

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(output_parsed=self.parsed, output=self.output)


def config(**overrides: object) -> OpenAIResearchConfig:
    values: dict[str, object] = {
        "api_key": "test-key",
        "model": "test-research-model",
        "language": "es-ES",
        "channel_id": "engineering-test",
        "max_sources": 5,
    }
    values.update(overrides)
    return OpenAIResearchConfig(**values)  # type: ignore[arg-type]


def make_provider(
    parsed: object, output: object | None = None, **config_overrides: object
) -> tuple[OpenAIResearchProvider, FakeResponses]:
    responses = FakeResponses(parsed, output)
    client = SimpleNamespace(responses=responses)
    return OpenAIResearchProvider(config(**config_overrides), client=client), responses


def test_request_uses_model_topic_search_tool_sources_and_schema() -> None:
    provider, responses = make_provider(research_payload(), max_sources=3)
    topic = Topic(id=uuid4(), title="¿Por qué los puentes tienen juntas de dilatación?")

    provider.research(topic)

    assert responses.kwargs["model"] == "test-research-model"
    assert responses.kwargs["text_format"] is OpenAIResearchResponse
    assert responses.kwargs["tools"] == [{"type": "web_search"}]
    assert responses.kwargs["tool_choice"] == "required"
    assert responses.kwargs["include"] == ["web_search_call.action.sources"]
    assert topic.title in str(responses.kwargs["input"])
    assert "up to 3" in str(responses.kwargs["input"])


def test_structured_output_schema_does_not_use_unsupported_uri_format() -> None:
    schema = OpenAIResearchResponse.model_json_schema()

    def formats(value: object) -> list[str]:
        if isinstance(value, dict):
            own = [str(value["format"])] if "format" in value else []
            return own + [item for child in value.values() for item in formats(child)]
        if isinstance(value, list):
            return [item for child in value for item in formats(child)]
        return []

    assert "uri" not in formats(schema)


def test_valid_response_maps_source_backed_research_result() -> None:
    provider, _ = make_provider(research_payload())
    topic = Topic(id=uuid4(), title="¿Por qué los puentes tienen juntas de dilatación?")

    result = provider.research(topic)

    assert result.topic_id == topic.id
    assert result.summary.startswith("Las juntas")
    assert len(result.key_facts) == 2
    assert str(result.sources[0].url) == _SOURCE_URL
    assert result.sources[0].title == "FHWA Bridge Preservation Guide"
    assert result.sources[0].retrieved_at.tzinfo is not None
    assert result.uncertainties


def test_duplicate_source_urls_are_rejected() -> None:
    source = research_payload()["sources"]
    assert isinstance(source, list)
    provider, _ = make_provider(research_payload(sources=[source[0], source[0]]))

    with pytest.raises(ResearchValidationError, match="duplicate"):
        provider.research(Topic(title="Tema"))


def test_source_not_returned_by_web_search_is_rejected() -> None:
    provider, _ = make_provider(
        research_payload(),
        web_output("https://highways.dot.gov/another-source"),
    )

    with pytest.raises(ResearchValidationError, match="not returned"):
        provider.research(Topic(title="Tema"))


@pytest.mark.parametrize(
    ("payload", "output"),
    [
        (research_payload(sources=[]), web_output()),
        (
            research_payload(sources=[{"title": "Bad", "url": "not-a-url", "publisher": "Bad"}]),
            web_output(),
        ),
        (research_payload(), []),
        (None, web_output()),
        ({}, web_output()),
    ],
)
def test_empty_invalid_or_ungrounded_research_is_rejected(payload: object, output: object) -> None:
    provider, _ = make_provider(payload, output)

    with pytest.raises(ResearchValidationError):
        provider.research(Topic(title="Tema"))


def test_source_count_above_configured_max_is_rejected() -> None:
    second_url = "https://highways.dot.gov/research"
    sources = research_payload()["sources"]
    assert isinstance(sources, list)
    second = {
        "title": "Highway Research",
        "url": second_url,
        "publisher": "US Department of Transportation",
    }
    provider, _ = make_provider(
        research_payload(sources=[sources[0], second]),
        web_output(),
        max_sources=1,
    )

    with pytest.raises(ResearchValidationError, match="more sources"):
        provider.research(Topic(title="Tema"))


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

    provider = OpenAIResearchProvider(
        config(), client=SimpleNamespace(responses=FailingResponses())
    )

    with pytest.raises(ResearchError, match=message):
        provider.research(Topic(title="Tema"))


def test_missing_key_fails_before_client_creation() -> None:
    with pytest.raises(ResearchError, match="OPENAI_API_KEY"):
        OpenAIResearchProvider(config(api_key=""))
