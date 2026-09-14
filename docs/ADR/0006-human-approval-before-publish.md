# ADR 0006 — Require Human Approval Before Publication

## Status

Accepted

## Context

The first versions of the system will rely on generated research, scripts, narration, and media. Fully autonomous publication would create unnecessary quality and reputational risk.

## Decision

A Short must reach an approved state before it can be published.

Expected flow:

```text
GENERATING
 -> RENDERED
 -> REVIEW_PENDING
 -> APPROVED
 -> PUBLISHED
```

## Consequences

The system is not initially fully autonomous, but quality control is preserved while the pipeline matures.
