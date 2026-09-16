# ADR 0016 - Narration-First Deterministic Audio Mix

## Status

Accepted

## Context

Persisted narration is the authoritative audio source. Optional music should be inexpensive to
iterate, never require new TTS or other AI calls, and never mask speech. FFmpeg owns the existing
render subprocess and final media validation.

## Decision

Channel `audio` configuration expresses target loudness, peak ceiling, one optional project-local
music path, gain, fades and ducking parameters. `RenderProjectUseCase` passes this intent through
the existing `RenderInputs`; the FFmpeg adapter translates it to filters. Music remains disabled
by default and is never fetched, generated or selected automatically.

FFmpeg measures narration with `loudnorm`, then uses those measurements for a second-pass
normalization in the render graph. Pure-silent narration bypasses unattainable normalization.
Music is gain-adjusted and faded before narration-driven `sidechaincompress`. Mixing uses
`amix=normalize=0` to preserve voice level, followed by a conservative limiter. The final AAC
stream is measured independently. Non-silent normalized output must be within 2 LU of target;
true peak must not exceed the configured ceiling by more than 0.25 dB. Source media is untouched.

## Consequences

- `render-project` can change all audio settings offline without upstream or alignment calls.
- Music must be supplied inside each project and appropriately licensed for publication.
- `audio-mix.json` records measured values and applied settings; the manifest stores only mixer
  identity and whether music was enabled.
- Silent fixture WAVs remain useful for media assembly but cannot prove audible mix quality.
