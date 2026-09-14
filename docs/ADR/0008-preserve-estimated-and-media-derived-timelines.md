# ADR 0008 — Preserve Estimated And Media-Derived Timelines

## Status

Accepted

## Context

Scene planning creates a creative storyboard with estimated durations before narration exists.
Once an audio artifact is generated, its measured duration is authoritative for rendering. Replacing
the estimated plan would lose the original creative intent and make timing adjustments impossible to
inspect or reproduce.

## Decision

Persist both contracts:

- `ScenePlan` in `scenes.json` remains the estimated storyboard.
- `TimedScenePlan` in `timed-scenes.json` is the render-ready timeline reconciled against narration.

Phase 3 uses a provider-independent proportional reconciliation strategy. It preserves scene order
and creative fields, starts at zero, keeps the timeline continuous, and sets the final scene end to
the measured narration duration exactly.

## Consequences

Positive:

- audio duration drives media timing without discarding planning intent;
- future renderers have an explicit media-aligned input;
- later TTS adapters can improve reconciliation with sentence or word timestamps without changing
  the original storyboard contract.

Negative:

- two timeline artifacts must be inspected and retained;
- proportional timing is an approximation until real speech timing data is available.
