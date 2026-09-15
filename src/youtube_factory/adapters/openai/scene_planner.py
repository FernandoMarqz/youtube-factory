"""OpenAI Structured Outputs adapter for semantic scene planning."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from youtube_factory.application.exceptions import ScenePlanningError, ScenePlanValidationError
from youtube_factory.application.services import normalize_estimated_scene_durations
from youtube_factory.domain.enums import AssetType
from youtube_factory.domain.models import Scene, ScenePlan, Script

NonEmptyText = Annotated[str, Field(min_length=1)]

_PLANNER_INSTRUCTIONS = """You plan the semantic visual scenes for a vertical YouTube Short.
Return structured output only. Copy every narration segment exactly from the supplied full
narration: do not paraphrase, invent, omit, duplicate, or reorder any wording. In sequence, the
segments must reconstruct the full narration. Choose visually distinct scenes within the supplied
count bounds without unnecessary fragmentation. Make every visual description concrete and state
separately why the visual exists. Prefer diagrams for explanatory geometry or mechanisms and
images for real-world views. Keep on-screen text optional and very short. Asset type must be image,
or animation. Animation describes future motion intent only; this stage still produces semantic
scene planning, not image prompts, images, video, subtitles, or final media timing."""


class OpenAIAssetType(StrEnum):
    """Asset choices supported by the current static-visual pipeline."""

    IMAGE = "image"
    DIAGRAM = "diagram"
    ANIMATION = "animation"


class OpenAISceneDTO(BaseModel):
    """Provider-specific structured scene returned by OpenAI."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    sequence: Annotated[int, Field(ge=1)]
    narration_segment: NonEmptyText
    visual_description: NonEmptyText
    visual_intent: NonEmptyText
    asset_type: OpenAIAssetType
    on_screen_text: Annotated[str, Field(min_length=1, max_length=60)] | None = None
    transition_suggestion: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    estimated_duration_seconds: Annotated[float, Field(gt=0)]


class OpenAIScenePlanResponse(BaseModel):
    """Provider DTO used directly as the Responses API structured-output schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenes: list[OpenAISceneDTO] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class OpenAIScenePlannerConfig:
    """Explicit provider and editorial settings assembled by the CLI composition root."""

    api_key: str
    model: str
    language: str
    channel_id: str
    min_scenes: int
    max_scenes: int
    target_scene_duration_seconds: float
    visual_style: str


class OpenAIScenePlanner:
    """Maps OpenAI structured semantic planning output into a validated ScenePlan."""

    identifier = "openai-scene-planner-v1"
    provider = "openai"
    model: str | None

    def __init__(self, config: OpenAIScenePlannerConfig, client: Any | None = None) -> None:
        if not config.api_key.strip():
            raise ScenePlanningError("OPENAI_API_KEY is required for OpenAI scene planning")
        if not config.model.strip():
            raise ScenePlanningError("OpenAI scene-planning model is required")
        if config.min_scenes <= 0 or config.max_scenes < config.min_scenes:
            raise ScenePlanningError("OpenAI scene-planning count bounds are invalid")
        if config.target_scene_duration_seconds <= 0:
            raise ScenePlanningError("target scene duration must be positive")
        self._config = config
        self.model = config.model
        self._client = client if client is not None else _create_openai_client(config.api_key)

    def plan(self, script: Script) -> ScenePlan:
        """Request structured semantic scenes and normalize their provisional timing."""
        try:
            response = self._client.responses.parse(
                model=self._config.model,
                instructions=_PLANNER_INSTRUCTIONS,
                input=self._build_input(script),
                text_format=OpenAIScenePlanResponse,
            )
        except Exception as error:
            raise ScenePlanningError(_openai_error_message(error)) from error

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ScenePlanValidationError("OpenAI returned an empty structured scene plan")
        try:
            provider_plan = OpenAIScenePlanResponse.model_validate(parsed)
        except ValidationError as error:
            raise ScenePlanValidationError(
                "OpenAI returned an invalid scene-plan schema"
            ) from error
        return self._to_domain_plan(script, provider_plan)

    def _to_domain_plan(self, script: Script, provider_plan: OpenAIScenePlanResponse) -> ScenePlan:
        scenes = provider_plan.scenes
        if not self._config.min_scenes <= len(scenes) <= self._config.max_scenes:
            raise ScenePlanValidationError("OpenAI scene count is outside configured bounds")
        if [scene.sequence for scene in scenes] != list(range(1, len(scenes) + 1)):
            raise ScenePlanValidationError(
                "OpenAI scene sequences must be contiguous and start at 1"
            )
        reconstructed = _normalize_whitespace(" ".join(scene.narration_segment for scene in scenes))
        if reconstructed != _normalize_whitespace(script.full_narration):
            raise ScenePlanValidationError(
                "OpenAI narration segments do not reconstruct the original script"
            )
        try:
            timings = normalize_estimated_scene_durations(
                [scene.estimated_duration_seconds for scene in scenes],
                script.estimated_duration_seconds,
            )
            domain_scenes = [
                Scene(
                    sequence=scene.sequence,
                    narration_segment=scene.narration_segment,
                    start_seconds=timing.start_seconds,
                    end_seconds=timing.end_seconds,
                    duration_seconds=timing.duration_seconds,
                    visual_description=scene.visual_description,
                    visual_intent=scene.visual_intent,
                    asset_type=AssetType(scene.asset_type.value),
                    on_screen_text=scene.on_screen_text,
                    transition_suggestion=scene.transition_suggestion,
                )
                for scene, timing in zip(scenes, timings, strict=True)
            ]
            return ScenePlan(
                topic_id=script.topic_id,
                scenes=domain_scenes,
                total_duration_seconds=script.estimated_duration_seconds,
            )
        except (ValidationError, ValueError) as error:
            raise ScenePlanValidationError(
                "OpenAI scene estimates could not form a valid provisional timeline"
            ) from error

    def _build_input(self, script: Script) -> str:
        config = self._config
        return (
            f"Channel: {config.channel_id}\n"
            f"Language: {config.language}\n"
            f"Visual style context: {config.visual_style}\n"
            f"Scene count: choose from {config.min_scenes} to {config.max_scenes}.\n"
            f"Target scene duration: about {config.target_scene_duration_seconds} seconds.\n"
            f"Script estimated total duration: {script.estimated_duration_seconds} seconds.\n\n"
            f"Hook:\n{script.hook}\n\n"
            f"Body:\n{script.body}\n\n"
            f"Ending:\n{script.ending}\n\n"
            f"Full narration to segment exactly:\n{script.full_narration}"
        )


def _normalize_whitespace(text: str) -> str:
    """Ignore only whitespace-run differences when checking exact narration reconstruction."""
    return " ".join(text.split())


def _create_openai_client(api_key: str) -> Any:
    try:
        from openai import OpenAI
    except ImportError as error:
        raise ScenePlanningError("OpenAI SDK is not installed") from error
    return OpenAI(api_key=api_key)


def _openai_error_message(error: Exception) -> str:
    error_name = type(error).__name__
    if error_name == "AuthenticationError":
        return "OpenAI scene-planning authentication failed"
    if error_name == "RateLimitError":
        return "OpenAI scene-planning rate limit reached"
    if error_name in {"APIConnectionError", "APITimeoutError"}:
        return "OpenAI scene-planning service is unavailable"
    return "OpenAI scene-planning request failed"
