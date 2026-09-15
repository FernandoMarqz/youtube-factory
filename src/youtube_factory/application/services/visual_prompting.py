"""Deterministic conversion from semantic scenes to provider-ready visual prompts."""

from typing import Protocol

from pydantic import ValidationError

from youtube_factory.application.config import ChannelConfig
from youtube_factory.application.exceptions import VisualPromptGenerationError
from youtube_factory.domain.models import TimedScenePlan, VisualPrompt, VisualPromptPlan


class VisualPromptBuilder(Protocol):
    """Application boundary for evolving visual prompt strategy independently."""

    identifier: str

    def build(
        self, timed_scene_plan: TimedScenePlan, channel_config: ChannelConfig
    ) -> VisualPromptPlan:
        """Create one provider-ready prompt for each timed scene."""


class DeterministicVisualPromptBuilder:
    """Build stable, channel-aware prompts without coupling scenes to a provider."""

    identifier = "deterministic-visual-prompts-v1"

    def build(
        self, timed_scene_plan: TimedScenePlan, channel_config: ChannelConfig
    ) -> VisualPromptPlan:
        """Create exactly one ordered prompt for every render-ready scene."""
        try:
            prompts = [
                VisualPrompt(
                    scene_sequence=scene.sequence,
                    prompt=self._prompt_text(
                        scene.visual_description, scene.visual_intent, channel_config
                    ),
                    exclusions=(
                        "captions, subtitles, watermarks, logos, UI elements, decorative text"
                    ),
                    visual_intent=scene.visual_intent,
                    asset_type=scene.asset_type,
                    width=channel_config.visuals.width,
                    height=channel_config.visuals.height,
                    aspect_ratio=channel_config.visuals.aspect_ratio,
                    style=channel_config.visuals.style,
                )
                for scene in timed_scene_plan.scenes
            ]
            plan = VisualPromptPlan(
                topic_id=timed_scene_plan.topic_id,
                channel_id=channel_config.id,
                prompts=prompts,
            )
        except (ValidationError, ValueError) as error:
            raise VisualPromptGenerationError(
                "could not build a valid visual prompt plan"
            ) from error
        if [prompt.scene_sequence for prompt in plan.prompts] != [
            scene.sequence for scene in timed_scene_plan.scenes
        ]:
            raise VisualPromptGenerationError("visual prompts do not correspond to timed scenes")
        return plan

    @staticmethod
    def _prompt_text(description: str, intent: str, channel: ChannelConfig) -> str:
        visual = channel.visuals
        return (
            f"Create a single {visual.aspect_ratio} vertical visual for concise educational "
            f"content in {channel.language}. Main visual idea: {description}. "
            f"Communication purpose: {intent}. Art direction: {visual.style}. "
            "Show one dominant subject with immediate visual clarity, polished realistic or "
            "illustrative detail, cinematic lighting, and clear foreground/background separation. "
            "Compose safely for a mobile Short, leaving uncluttered upper and lower regions for "
            "captions added later. Do not include captions, subtitles, watermarks, logos, UI "
            "elements, or decorative text."
        )
