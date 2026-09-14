"""Reconcile creative timing estimates with measured media duration."""

from decimal import ROUND_HALF_UP, Decimal

from youtube_factory.domain.models import Narration, Scene, ScenePlan, TimedScenePlan

PROPORTIONAL_RECONCILIATION_STRATEGY = "proportional-v1"
_MILLISECONDS = Decimal("0.001")


class SceneTimingReconciler:
    """Scales an estimated storyboard into a narration-aligned render timeline."""

    strategy_identifier = PROPORTIONAL_RECONCILIATION_STRATEGY

    def reconcile(self, scene_plan: ScenePlan, narration: Narration) -> TimedScenePlan:
        """Scale scenes proportionally and set the last boundary to measured audio duration."""
        if scene_plan.topic_id != narration.topic_id:
            raise ValueError("scene plan and narration must belong to the same topic")
        estimated = Decimal(str(scene_plan.total_duration_seconds))
        actual = Decimal(str(narration.duration_seconds))
        scale_factor = actual / estimated
        reconciled_scenes: list[Scene] = []
        current_start = Decimal("0")
        final_index = len(scene_plan.scenes) - 1
        for index, scene in enumerate(scene_plan.scenes):
            scaled_end = (
                actual
                if index == final_index
                else _round_milliseconds(Decimal(str(scene.end_seconds)) * scale_factor)
            )
            duration = scaled_end - current_start
            reconciled_scenes.append(
                scene.model_copy(
                    update={
                        "start_seconds": float(current_start),
                        "end_seconds": float(scaled_end),
                        "duration_seconds": float(duration),
                    }
                )
            )
            current_start = scaled_end
        return TimedScenePlan(
            topic_id=scene_plan.topic_id,
            source_total_duration_seconds=scene_plan.total_duration_seconds,
            narration_duration_seconds=narration.duration_seconds,
            total_duration_seconds=narration.duration_seconds,
            reconciliation_strategy=self.strategy_identifier,
            scenes=reconciled_scenes,
        )


def _round_milliseconds(value: Decimal) -> Decimal:
    """Round intermediate boundaries to milliseconds without changing the final boundary."""
    return value.quantize(_MILLISECONDS, rounding=ROUND_HALF_UP)
