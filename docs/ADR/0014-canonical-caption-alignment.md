# ADR 0014 - Canonical Caption Text With Acoustic Timing

## Status

Accepted

## Context

The narration WAV is the real timing source, but transcription can change punctuation, accents,
or words. Caption text must remain exactly what was sent to TTS, and caption grouping must be
reproducible without a second LLM.

## Decision

`CaptionAlignmentProvider` supplies word timing. The OpenAI adapter uses the documented
`whisper-1` transcription API with `verbose_json` and word granularity; the local adapter uses
clearly labeled synthetic timing only for offline assembly. Canonical narration tokens are
reconciled against acoustic tokens by ordered normalized character matching. Normalization is
comparison-only. Below 90% matched canonical tokens, or when an unmatched token has no timing
gap, alignment fails explicitly. `CaptionPlanner` deterministically groups canonical words, and
ASS is a style-derived render input. `captions.json` remains the semantic artifact.

The renderer burns ASS via libass after concatenating visuals. The fixed relative path and
project working directory avoid platform-specific filter escaping. When captions are absent or
disabled, Phase 5 rendering remains unchanged.

## Consequences

- A paid transcription is needed once for accurate speech captions; style rerenders need none.
- Misrecognized speech cannot silently rewrite captions.
- Local synthetic timing is useful for assembly but is not a quality substitute for real alignment.
