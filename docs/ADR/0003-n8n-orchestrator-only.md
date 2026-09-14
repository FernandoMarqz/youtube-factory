# ADR 0003 — n8n Is An Orchestrator Only

## Status

Accepted

## Context

n8n is useful for scheduling, notifications, and external workflow coordination, but embedding business rules, prompts, rendering rules, and data transformations inside workflow nodes makes systems difficult to test and version.

## Decision

Use n8n only to orchestrate application capabilities exposed through CLI or HTTP interfaces.

## Consequences

Core behavior remains:

- version controlled
- unit testable
- reusable without n8n
- easier to migrate to another orchestrator
