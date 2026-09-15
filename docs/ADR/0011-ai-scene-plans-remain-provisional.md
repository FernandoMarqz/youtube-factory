# ADR 0011 — AI Scene Plans Remain Semantic And Provisional

## Status

Accepted

## Context

An AI planner can choose useful narration segments, visual ideas and relative pacing for arbitrary
scripts, but its output is untrusted and is created before narration media exists. Treating model
timestamps as final would conflict with the established rule that measured audio duration drives
render timing.

## Decision

Keep `ScenePlanner` provider-neutral and provide local and OpenAI adapters. The OpenAI adapter uses
provider-private Pydantic Structured Output DTOs, then deterministically validates scene count,
sequence and complete narration reconstruction. Only whitespace runs are normalized during the
reconstruction comparison; narration content is never repaired.

AI duration values are relative weights. A provider-neutral application service scales them to
`Script.estimated_duration_seconds`, with continuous millisecond boundaries and an exact final end.
This provisional plan is persisted as `scenes.json`. The existing `SceneTimingReconciler` remains
unchanged and produces media-authoritative `timed-scenes.json` after narration generation.

## Consequences

Positive:

- arbitrary scripts can receive dynamic visual planning without changing the domain or use case;
- invalid or hallucinated narration segmentation stops before paid downstream stages;
- estimated creative pacing and real media timing remain separately inspectable;
- deterministic local planning remains available for offline tests.

Negative:

- model output can fail even when its JSON schema is valid;
- whitespace-normalized reconstruction deliberately rejects all non-whitespace editorial changes;
- arbitrary topics still depend on future non-fixture research and script providers upstream.
