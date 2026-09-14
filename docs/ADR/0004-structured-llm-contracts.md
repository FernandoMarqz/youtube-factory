# ADR 0004 — Validate LLM Output Through Structured Contracts

## Status

Accepted

## Context

The pipeline contains multiple AI-generated stages. Passing arbitrary free-form text between stages makes failures difficult to detect and reproduce.

## Decision

LLM-generated data crossing application boundaries must use explicit structured models validated with Pydantic.

Examples include:

- ResearchResult
- Script
- ScenePlan

## Consequences

Positive:

- deterministic validation
- easier testing
- clearer failure handling
- provider independence

Negative:

- schemas require maintenance as the product evolves
