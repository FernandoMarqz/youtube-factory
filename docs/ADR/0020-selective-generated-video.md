# ADR 0020 - Selective Generated Video Is An Optional Persisted Enhancement

## Status

Accepted

## Decision

Keep `TimedScenePlan` authoritative and Phase 8B still-image beats as the always-available
fallback. A deterministic, free policy may select at most one long animation-intent scene
whose second beat fits the five-second budget. The selected scene and prompt are persisted
before any paid provider operation. Generation requires an explicit CLI command or flag and
an enabled channel setting. `render-project` never invokes a video provider.

The business port is `VideoAssetProvider`; Runway Gen-4.5 is one adapter, not a renderer
dependency. Downloaded clips are validated, stored separately from their PNG source, and
never replaced without explicit regeneration. FFmpeg may substitute a valid clip for the second
beat, normalizing its geometry, FPS and exact frame count. Provider audio is not mapped; the
established narration/music mix and ASS captions remain downstream.

## Consequences

Projects remain renderable offline when no generated clip exists or a stored clip is invalid.
Generated clips must be reviewed for factual and visual coherence before publication. Output
metadata records task ID, source/prompt hashes and requested seconds, not estimated cost.
