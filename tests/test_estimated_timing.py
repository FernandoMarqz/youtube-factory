"""Tests for deterministic provisional scene timing normalization."""

import pytest

from youtube_factory.application.services import normalize_estimated_scene_durations


def test_relative_estimates_are_scaled_to_exact_total_without_gaps() -> None:
    timings = normalize_estimated_scene_durations([3.0, 4.0, 5.0], 34.0)

    assert timings[0].start_seconds == 0.0
    assert timings[-1].end_seconds == 34.0
    assert all(
        previous.end_seconds == current.start_seconds
        for previous, current in zip(timings, timings[1:], strict=False)
    )
    assert sum(timing.duration_seconds for timing in timings) == pytest.approx(34.0)


@pytest.mark.parametrize("durations", [[], [1.0, 0.0], [1.0, -1.0]])
def test_invalid_relative_estimates_fail(durations: list[float]) -> None:
    with pytest.raises(ValueError):
        normalize_estimated_scene_durations(durations, 20.0)
