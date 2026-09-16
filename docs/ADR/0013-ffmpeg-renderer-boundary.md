# ADR 0013 - FFmpeg Behind A Renderer Port

## Status

Accepted

## Context

Phase 4 persists a normalized mono PCM WAV, a narration-derived `TimedScenePlan`, and one PNG
per scene. Rendering needs real filesystem paths, subprocess execution and ffprobe inspection,
none of which belong in application or domain logic.

## Decision

The application calls a provider-neutral `Renderer` port with validated persisted `RenderInputs`
and typed `RenderConfig`. `FileSystemArtifactStore` loads and validates the input media and persists
`render.json` plus manifest changes. `FFmpegRenderer` alone discovers executables through PATH,
constructs argument arrays, executes media commands and parses ffprobe JSON.

`TimedScenePlan` is the only render timeline. Each static PNG is held for the difference between
its rounded start and end frame boundaries. Images are scaled preserving aspect ratio to cover
1080x1920, then cropped symmetrically at the center. Scenes use hard cuts. The existing WAV is
muxed as AAC. No subtitles, motion or background audio are added.

The final MP4 is accepted only after ffprobe confirms streams, codecs, dimensions, pixel format,
frame rate and a duration within two configured frames of the narration-derived timeline. Two
frames allow video frame rounding and AAC/container tail rounding.

## Consequences

- The render-only command can use existing paid media with zero upstream provider calls.
- FFmpeg/ffprobe must be installed and on PATH for rendering. Tests without them still run.
- A failed render leaves the persisted upstream artifacts available for inspection and retry.
