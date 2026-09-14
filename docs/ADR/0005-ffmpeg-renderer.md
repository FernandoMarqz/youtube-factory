# ADR 0005 — Use FFmpeg As The Initial Renderer

## Status

Accepted

## Context

The initial product does not require expensive end-to-end generative video. High-quality Shorts can be produced from still assets, narration, subtitles, overlays, and motion effects.

## Decision

Use FFmpeg as the first rendering engine.

## Consequences

Positive:

- low cost
- deterministic output
- automation-friendly
- powerful media composition

Negative:

- advanced editing logic can become complex

Mitigation:

Keep rendering logic isolated behind a `Renderer` port and organize visual styles as reusable templates.
