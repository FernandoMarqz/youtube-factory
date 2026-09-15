"""OpenAI Structured Outputs adapter for grounded Short script generation."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from youtube_factory.application.exceptions import ScriptGenerationError, ScriptValidationError
from youtube_factory.application.services import estimate_spoken_duration_seconds
from youtube_factory.domain.enums import HookType
from youtube_factory.domain.models import ResearchResult, Script, Topic

NonEmptyText = Annotated[str, Field(min_length=1)]

_SCRIPT_INSTRUCTIONS = """Write a concise spoken script for a YouTube Short. Use only the supplied
research as factual grounding. Do not browse, independently research, or introduce any factual
claim not supported by the supplied key facts. If a useful fact is absent, omit it. Optimize for an
immediate hook, curiosity, clarity, high information density, natural conversational delivery, no
misleading clickbait, no filler, and a clear payoff. Return semantic components only as structured
output. Do not return full_narration or a numeric duration; application code derives both."""


class OpenAIHookType(StrEnum):
    """Hook choices supported by the provider-neutral Script contract."""

    QUESTION = "question"
    SURPRISING_FACT = "surprising_fact"
    PROBLEM = "problem"
    CONTRAST = "contrast"


class OpenAIScriptResponse(BaseModel):
    """Provider-private structured script components."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    hook: NonEmptyText
    body: NonEmptyText
    ending: NonEmptyText
    hook_type: OpenAIHookType
    supporting_fact_indices: list[Annotated[int, Field(ge=1)]] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class OpenAIScriptConfig:
    """Explicit model and editorial settings supplied by application composition."""

    api_key: str
    model: str
    language: str
    channel_id: str
    niche: str
    target_duration_seconds: int
    min_duration_seconds: int
    max_duration_seconds: int


class OpenAIScriptGenerator:
    """Generate arbitrary-topic scripts grounded exclusively in a ResearchResult."""

    identifier = "openai-script-v1"
    provider = "openai"
    model: str | None

    def __init__(self, config: OpenAIScriptConfig, client: Any | None = None) -> None:
        if not config.api_key.strip():
            raise ScriptGenerationError("OPENAI_API_KEY is required for OpenAI script generation")
        if not config.model.strip():
            raise ScriptGenerationError("OpenAI script model is required")
        if not 0 < config.min_duration_seconds <= config.target_duration_seconds:
            raise ScriptGenerationError("script duration configuration is invalid")
        if config.max_duration_seconds < config.target_duration_seconds:
            raise ScriptGenerationError("script duration configuration is invalid")
        self._config = config
        self.model = config.model
        self._client = client if client is not None else _create_openai_client(config.api_key)

    def generate(self, topic: Topic, research: ResearchResult) -> Script:
        """Request grounded components and construct duplicate fields deterministically."""
        if research.topic_id != topic.id:
            raise ScriptValidationError("research does not belong to the requested topic")
        try:
            response = self._client.responses.parse(
                model=self._config.model,
                instructions=_SCRIPT_INSTRUCTIONS,
                input=self._build_input(topic, research),
                text_format=OpenAIScriptResponse,
            )
        except Exception as error:
            raise ScriptGenerationError(_openai_error_message(error)) from error

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ScriptValidationError("OpenAI returned an empty structured script")
        try:
            provider_script = OpenAIScriptResponse.model_validate(parsed)
        except ValidationError as error:
            raise ScriptValidationError("OpenAI returned an invalid script schema") from error
        return self._to_domain_script(topic, research, provider_script)

    def _to_domain_script(
        self,
        topic: Topic,
        research: ResearchResult,
        provider_script: OpenAIScriptResponse,
    ) -> Script:
        indices = provider_script.supporting_fact_indices
        if len(set(indices)) != len(indices):
            raise ScriptValidationError("OpenAI script repeated a supporting fact index")
        if any(index > len(research.key_facts) for index in indices):
            raise ScriptValidationError("OpenAI script referenced an unknown research fact")

        full_narration = " ".join(
            (provider_script.hook, provider_script.body, provider_script.ending)
        )
        estimated_duration = estimate_spoken_duration_seconds(full_narration)
        if not (
            self._config.min_duration_seconds
            <= estimated_duration
            <= self._config.max_duration_seconds
        ):
            raise ScriptValidationError(
                "generated script duration is outside configured Short bounds"
            )
        try:
            return Script(
                topic_id=topic.id,
                hook=provider_script.hook,
                body=provider_script.body,
                ending=provider_script.ending,
                full_narration=full_narration,
                hook_type=HookType(provider_script.hook_type.value),
                estimated_duration_seconds=estimated_duration,
                claims=[research.key_facts[index - 1] for index in indices],
            )
        except ValidationError as error:
            raise ScriptValidationError(
                "OpenAI script could not form a valid domain contract"
            ) from error

    def _build_input(self, topic: Topic, research: ResearchResult) -> str:
        facts = "\n".join(
            f"{index}. {fact}" for index, fact in enumerate(research.key_facts, start=1)
        )
        uncertainties = "\n".join(f"- {value}" for value in research.uncertainties) or "- None"
        sources = "\n".join(
            f"- {source.title} ({source.publisher}): {source.url}" for source in research.sources
        )
        return (
            f"Channel: {self._config.channel_id}\n"
            f"Language: {self._config.language}\n"
            f"Niche: {self._config.niche}\n"
            f"Topic: {topic.title}\n"
            f"Target duration: about {self._config.target_duration_seconds} seconds; accepted "
            f"range {self._config.min_duration_seconds}-{self._config.max_duration_seconds} "
            "seconds at roughly 150 spoken words per minute.\n\n"
            f"Research summary:\n{research.summary}\n\n"
            f"Allowed factual key facts (reference by 1-based index):\n{facts}\n\n"
            f"Uncertainties that must be respected:\n{uncertainties}\n\n"
            f"Source context for traceability:\n{sources}"
        )


def _create_openai_client(api_key: str) -> Any:
    try:
        from openai import OpenAI
    except ImportError as error:
        raise ScriptGenerationError("OpenAI SDK is not installed") from error
    return OpenAI(api_key=api_key)


def _openai_error_message(error: Exception) -> str:
    error_name = type(error).__name__
    if error_name == "AuthenticationError":
        return "OpenAI script-generation authentication failed"
    if error_name == "RateLimitError":
        return "OpenAI script-generation rate limit reached"
    if error_name in {"APIConnectionError", "APITimeoutError"}:
        return "OpenAI script-generation service is unavailable"
    return "OpenAI script-generation request failed"
