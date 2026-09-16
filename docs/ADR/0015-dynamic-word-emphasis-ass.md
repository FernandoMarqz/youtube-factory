# ADR 0015 - Word Timing Drives Render-Only ASS Emphasis

## Status

Accepted

## Context

Phase 6 persists canonical word alignment and readable caption cues. Style iteration must not
repeat transcription or alter cue grouping. A highlighted word must not shift its neighbors.

## Decision

New cues persist half-open word-index ranges. Older cues without indexes are mapped in sequence
only when every canonical token matches and every word lies inside its cue. `WordAlignment` remains
the timing source and `CaptionPlan` remains the grouping source.

Generate sequential, non-overlapping ASS dialogue events for each visible caption state. Each
event repeats the same canonical text and line break; only an inline primary-color override on
the acoustically active word differs. This avoids overlapping duplicate text and the cumulative
timing and gap semantics of karaoke tags. Silence gaps show the inactive color. Boundaries are
rounded independently from absolute seconds to ASS centiseconds. The existing libass filter and
FFmpeg renderer are unchanged.

## Consequences

- Style-only `render-project` runs need no provider calls and do not rewrite either semantic JSON.
- The ASS file has more events, but cue geometry and text stay stable.
- Visual onset precision is limited by ASS centiseconds and the output frame rate.
