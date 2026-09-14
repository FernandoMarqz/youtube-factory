# ADR 0007 — Ports And Deterministic Local Adapters Before External AI

## Status

Accepted

## Context

The first content-engine milestone must prove the `Topic -> ResearchResult -> Script`
orchestration, validation, artifact persistence, and CLI workflow without network access,
provider credentials, or nondeterministic model output.

## Decision

Define explicit `ResearchProvider`, `ScriptGenerator`, and `ProjectArtifactStore` ports.
Phase 1 supplies deterministic local implementations for the reference topic and a local
filesystem store. The application use case depends only on these ports and domain models.

The local providers are intentionally fixture-like. They use stable identifiers, timestamps,
and content so a repeated command for the same topic produces the same project identifier and
JSON artifacts.

## Consequences

Positive:

- the end-to-end workflow is executable offline;
- contracts and orchestration are testable before introducing AI providers;
- future AI-backed research and script adapters can replace local adapters without changing the
  use case or CLI contract.

Negative:

- Phase 1 supports only the reference topic;
- generated content is deliberately static and is not evidence of production research quality.
