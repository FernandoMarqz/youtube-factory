# ADR 0018 - Motion Is Derived Render Styling

## Status

Accepted

## Decision

Persisted PNGs remain source visuals and `TimedScenePlan` remains the only render timeline.
An application planner derives a provider-neutral `VisualMotionPlan` from timed scenes, asset
metadata and typed channel style. Stable topic/scene hashing provides variety without randomness.
`render-project` rebuilds and persists `visual-motion.json` on each successful render; this
allows offline style changes without regenerating any semantic or paid artifact.

FFmpeg executes the plan with bounded `zoompan` crops. Each scene is trimmed to its rounded
authoritative frame count before concatenation. Captions are applied after visual composition;
the Phase 7 audio graph is unchanged. All transitions remain hard cuts: overlapping crossfades
would shift caption-visible scene boundaries unless a separate frame-accurate policy is designed.

## Consequences

- Motion can be disabled to retain static-image rendering.
- No video model, image regeneration, network call or new timing source is needed.
- The motion plan is inspectable, but source scene/audio/caption/music artifacts are unchanged.
