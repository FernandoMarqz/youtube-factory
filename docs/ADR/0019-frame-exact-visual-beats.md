# ADR 0019 - Frame-Exact Intra-Scene Visual Beats

## Status

Accepted

## Decision

Keep `TimedScenePlan` as the only scene timeline and Phase 8 `VisualMotionPlan` as scene-level
style. A deterministic application planner derives one or two `VisualBeat` entries per scene
from the same persisted PNG. Beat boundaries use absolute rounded scene frames, not sums of
independently rounded seconds. The final beat ends at the scene boundary.

Animation-intent scenes qualify for two beats sooner than ordinary images; diagrams remain
single-beat. A stable hash chooses a mild split ratio. The second beat begins at the first
beat's terminal crop and zoom, then changes trajectory within Phase 8 bounds. Beat-level motion
is render styling, persisted in `visual-pacing.json` and rebuilt offline on `render-project`.

FFmpeg prepares the image once, splits that source to two `zoompan` branches where needed, and
concatenates beat video before its existing scene concat. Hard cuts remain; captions and audio
stay downstream and unchanged. No new image, narration segment, API call or semantic scene exists.
