"""OpenAI web-search adapter for source-backed arbitrary-topic research."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, ValidationError

from youtube_factory.application.exceptions import ResearchError, ResearchValidationError
from youtube_factory.domain.models import ResearchResult, Source, Topic

NonEmptyText = Annotated[str, Field(min_length=1)]
_HTTP_URL = TypeAdapter(HttpUrl)

_RESEARCH_INSTRUCTIONS = """You are a careful research assistant for short educational videos.
Use web search for the supplied topic. Prefer primary sources, official documentation,
government or institutional sources, recognized engineering/scientific references, and reputable
technical publications. Avoid SEO spam, social posts, and unsourced summaries. Return concise,
source-backed facts only. Preserve qualifications and context-dependent claims in uncertainties.
Every source URL in the structured output must be a real URL encountered through web search.
Do not invent sources or URLs. Return structured output only."""


class OpenAIResearchSource(BaseModel):
    """Provider-specific description of one source used by the research response."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    title: NonEmptyText
    # Responses structured-output schemas do not accept Pydantic's `uri` format.
    # The domain Source model validates this text as an HTTP URL after tool evidence is checked.
    url: NonEmptyText
    publisher: NonEmptyText
    notes: NonEmptyText | None = None


class OpenAIResearchResponse(BaseModel):
    """Structured research payload returned by the Responses API."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    summary: NonEmptyText
    key_facts: list[NonEmptyText] = Field(min_length=1)
    sources: list[OpenAIResearchSource] = Field(min_length=1)
    uncertainties: list[NonEmptyText] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class OpenAIResearchConfig:
    """Explicit OpenAI and editorial settings assembled at the composition root."""

    api_key: str
    model: str
    language: str
    channel_id: str
    max_sources: int


@dataclass(frozen=True, slots=True)
class _WebSourceEvidence:
    url: str
    title: str | None


class OpenAIResearchProvider:
    """Research arbitrary topics with OpenAI web search and verified source metadata."""

    identifier = "openai-research-v1"
    provider = "openai"
    model: str | None

    def __init__(self, config: OpenAIResearchConfig, client: Any | None = None) -> None:
        if not config.api_key.strip():
            raise ResearchError("OPENAI_API_KEY is required for OpenAI research")
        if not config.model.strip():
            raise ResearchError("OpenAI research model is required")
        if config.max_sources <= 0:
            raise ResearchError("maximum research source count must be positive")
        self._config = config
        self.model = config.model
        self._client = client if client is not None else _create_openai_client(config.api_key)

    def research(self, topic: Topic) -> ResearchResult:
        """Use web search, validate cited URLs and map the result to the domain contract."""
        try:
            response = self._client.responses.parse(
                model=self._config.model,
                instructions=_RESEARCH_INSTRUCTIONS,
                input=self._build_input(topic),
                tools=[{"type": "web_search"}],
                tool_choice="required",
                include=["web_search_call.action.sources"],
                text_format=OpenAIResearchResponse,
            )
        except Exception as error:
            raise ResearchError(_openai_error_message(error)) from error

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ResearchValidationError("OpenAI returned an empty structured research result")
        try:
            provider_result = OpenAIResearchResponse.model_validate(parsed)
        except ValidationError as error:
            raise ResearchValidationError("OpenAI returned an invalid research schema") from error
        return self._to_domain_result(topic, provider_result, response)

    def _to_domain_result(
        self,
        topic: Topic,
        provider_result: OpenAIResearchResponse,
        response: object,
    ) -> ResearchResult:
        if len(provider_result.sources) > self._config.max_sources:
            raise ResearchValidationError("OpenAI returned more sources than configured")

        evidence = _extract_web_source_evidence(response)
        if not evidence:
            raise ResearchValidationError("OpenAI research returned no usable web-search sources")

        normalized_urls = [_normalize_url(str(source.url)) for source in provider_result.sources]
        if len(set(normalized_urls)) != len(normalized_urls):
            raise ResearchValidationError("OpenAI research returned duplicate source URLs")

        missing_urls = [url for url in normalized_urls if url not in evidence]
        if missing_urls:
            raise ResearchValidationError(
                "OpenAI research cited a URL not returned by the web-search tool"
            )

        retrieved_at = datetime.now(UTC)
        try:
            sources = [
                Source(
                    title=evidence[url].title or provider_source.title,
                    url=_HTTP_URL.validate_python(provider_source.url),
                    publisher=provider_source.publisher,
                    retrieved_at=retrieved_at,
                    notes=provider_source.notes,
                )
                for provider_source, url in zip(
                    provider_result.sources, normalized_urls, strict=True
                )
            ]
            return ResearchResult(
                topic_id=topic.id,
                summary=provider_result.summary,
                key_facts=provider_result.key_facts,
                sources=sources,
                uncertainties=provider_result.uncertainties,
            )
        except ValidationError as error:
            raise ResearchValidationError(
                "OpenAI research could not form a valid domain result"
            ) from error

    def _build_input(self, topic: Topic) -> str:
        return (
            f"Channel: {self._config.channel_id}\n"
            f"Output language: {self._config.language}\n"
            f"Topic: {topic.title}\n"
            f"Return up to {self._config.max_sources} distinct high-quality sources. Aim for 2 or "
            "more when enough reliable sources exist, but always include at least one. Keep the "
            "result concise enough for a YouTube Short research artifact."
        )


def _extract_web_source_evidence(response: object) -> dict[str, _WebSourceEvidence]:
    """Extract URLs included by Responses API web-search calls without trusting model prose."""
    evidence: dict[str, _WebSourceEvidence] = {}
    output = _field(response, "output")
    if not isinstance(output, (list, tuple)):
        return evidence
    for item in output:
        if _field(item, "type") != "web_search_call":
            continue
        action = _field(item, "action")
        sources = _field(action, "sources")
        if not isinstance(sources, (list, tuple)):
            continue
        for source in sources:
            url = _field(source, "url")
            title = _field(source, "title")
            if isinstance(url, str) and url.strip():
                normalized = _normalize_url(url)
                evidence[normalized] = _WebSourceEvidence(
                    url=url,
                    title=title.strip() if isinstance(title, str) and title.strip() else None,
                )
    return evidence


def _field(value: object, name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    normalized_path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), normalized_path, parts.query, "")
    )


def _create_openai_client(api_key: str) -> Any:
    try:
        from openai import OpenAI
    except ImportError as error:
        raise ResearchError("OpenAI SDK is not installed") from error
    return OpenAI(api_key=api_key)


def _openai_error_message(error: Exception) -> str:
    error_name = type(error).__name__

    if error_name == "AuthenticationError":
        return "OpenAI research authentication failed"

    if error_name == "RateLimitError":
        return "OpenAI research rate limit reached"

    if error_name in {"APIConnectionError", "APITimeoutError"}:
        return "OpenAI research service is unavailable"

    return f"OpenAI research request failed: {error_name}: {error}"
