"""Free, deterministic eligibility and prompt planning for selective video."""

import re
import unicodedata
from math import ceil

from youtube_factory.application.config import GenerativeVideoConfig
from youtube_factory.application.exceptions import GenerativeVideoError
from youtube_factory.domain.enums import AssetType
from youtube_factory.domain.models import (
    GenerativeVideoPlan,
    PlannedVideoScene,
    ScenePlan,
    TimedScenePlan,
    VisualAssetManifest,
    VisualPacingPlan,
)

IDENTIFIER = "selective-generative-video-v1"
_TRANSFORMATION = (
    "transformacion",
    "transforma",
    "redondeada",
    "redondearlas",
    "cambia de",
    "se convierte",
    "reemplaza",
)
_PHYSICAL = ("presion", "grieta", "fluye", "propaga", "expande", "contrae", "gira")


def _normalize(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(character for character in plain if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", plain))


def _contains(text: str, phrase: str) -> bool:
    return f" {_normalize(phrase)} " in f" {text} "


class VideoPromptBuilder:
    """Describe only the scene's intended temporal action and preservation rules."""

    @staticmethod
    def build(description: str, intent: str, narration_segment: str) -> str:
        return (
            "Animate this existing vertical educational illustration. Motion and temporal "
            f"change strictly from the scene: {description} Intent: {intent} "
            f"Spoken context: {narration_segment} "
            "Preserve the original composition, subject identity, colors, geometry, "
            "educational style and vertical framing. Stable subtle camera. "
            "Do not introduce new objects or factual mechanisms. No new text, labels, "
            "subtitles, logos or watermarks as scene content; no distorted geometry."
        )


class GenerativeVideoEligibilityPolicy:
    """Rank only long animation-intent scenes with a second Phase 8B beat."""

    def plan(
        self,
        timed: TimedScenePlan,
        semantic: ScenePlan,
        visuals: VisualAssetManifest,
        pacing: VisualPacingPlan,
        config: GenerativeVideoConfig,
    ) -> GenerativeVideoPlan:
        if (
            timed.topic_id != visuals.topic_id
            or timed.topic_id != pacing.topic_id
            or timed.topic_id != semantic.topic_id
            or len(timed.scenes) != len(visuals.assets)
            or len(timed.scenes) != len(pacing.scenes)
            or len(timed.scenes) != len(semantic.scenes)
        ):
            raise GenerativeVideoError("generative video planning inputs differ")
        candidates: list[PlannedVideoScene] = []
        for scene, intent, image, paced in zip(
            timed.scenes, semantic.scenes, visuals.assets, pacing.scenes, strict=True
        ):
            if (
                scene.sequence != intent.sequence
                or scene.sequence != image.scene_sequence
                or scene.sequence != paced.scene_sequence
            ):
                raise GenerativeVideoError("generative video scene and image mapping differs")
            eligible = (
                intent.asset_type == AssetType.ANIMATION
                and scene.duration_seconds >= config.minimum_scene_duration_seconds
                and len(paced.beats) == 2
            )
            text = _normalize(f"{intent.visual_description} {intent.visual_intent}")
            reasons: list[str] = []
            score = 0
            if eligible:
                reasons.append("animation_intent")
                if scene.duration_seconds >= 8:
                    score += 3
                    reasons.append("long_scene")
                if any(_contains(text, word) for word in _TRANSFORMATION):
                    score += 4
                    reasons.append("transformation")
                if any(_contains(text, word) for word in _PHYSICAL):
                    score += 2
                    reasons.append("physical_process")
                matched = [word for word in config.dynamic_motion_keywords if _contains(text, word)]
                if matched:
                    score += 3
                    reasons.append("dynamic_keyword")
            target = min(5, config.budget.max_generated_seconds) if eligible else 0
            # A clip must cover the complete second beat; never stretch or loop it.
            if eligible and (target < 2 or ceil(paced.beats[1].frame_count / pacing.fps) > target):
                eligible = False
                reasons = []
                score = 0
                target = 0
            candidates.append(
                PlannedVideoScene(
                    scene_sequence=scene.sequence,
                    eligible=eligible,
                    selected=False,
                    score=score,
                    source_asset=image.file_path,
                    target_duration_seconds=target,
                    reasons=tuple(reasons),
                    prompt=(
                        VideoPromptBuilder.build(
                            intent.visual_description,
                            intent.visual_intent,
                            intent.narration_segment,
                        )
                        if eligible
                        else None
                    ),
                )
            )
        eligible_indexes = sorted(
            (index for index, item in enumerate(candidates) if item.eligible),
            key=lambda index: (-candidates[index].score, candidates[index].scene_sequence),
        )
        selected_indexes = set(eligible_indexes[: config.budget.max_generated_scenes])
        remaining = config.budget.max_generated_seconds
        for index in eligible_indexes:
            item = candidates[index]
            if index in selected_indexes and item.target_duration_seconds <= remaining:
                candidates[index] = item.model_copy(update={"selected": True})
                remaining -= item.target_duration_seconds
        return GenerativeVideoPlan(
            identifier=IDENTIFIER,
            topic_id=timed.topic_id,
            provider=config.provider,
            model=config.model,
            max_generated_scenes=config.budget.max_generated_scenes,
            max_generated_seconds=config.budget.max_generated_seconds,
            scenes=candidates,
        )
