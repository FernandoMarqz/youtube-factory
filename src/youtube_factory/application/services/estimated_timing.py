"""Deterministic provisional timing normalization for semantic scene plans."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from math import isfinite

_MILLISECONDS = Decimal("0.001")


@dataclass(frozen=True, slots=True)
class EstimatedSceneTiming:
    """One continuous provisional scene boundary."""

    start_seconds: float
    end_seconds: float
    duration_seconds: float


def normalize_estimated_scene_durations(
    relative_durations: Sequence[float], total_duration_seconds: float
) -> tuple[EstimatedSceneTiming, ...]:
    """Scale positive relative durations to an exact, millisecond-aligned total."""
    if not relative_durations:
        raise ValueError("at least one estimated scene duration is required")
    if not isfinite(total_duration_seconds) or total_duration_seconds <= 0:
        raise ValueError("estimated total duration must be positive and finite")
    if any(not isfinite(duration) or duration <= 0 for duration in relative_durations):
        raise ValueError("estimated scene durations must be positive and finite")

    weights = [Decimal(str(duration)) for duration in relative_durations]
    total = Decimal(str(total_duration_seconds))
    weight_sum = sum(weights, start=Decimal("0"))
    current_start = Decimal("0")
    cumulative_weight = Decimal("0")
    timings: list[EstimatedSceneTiming] = []

    for index, weight in enumerate(weights):
        cumulative_weight += weight
        end = (
            total
            if index == len(weights) - 1
            else (total * cumulative_weight / weight_sum).quantize(
                _MILLISECONDS, rounding=ROUND_HALF_UP
            )
        )
        if end <= current_start:
            raise ValueError("normalized scene duration is too short at millisecond precision")
        timings.append(
            EstimatedSceneTiming(
                start_seconds=float(current_start),
                end_seconds=float(end),
                duration_seconds=float(end - current_start),
            )
        )
        current_start = end
    return tuple(timings)
