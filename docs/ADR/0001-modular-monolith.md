# ADR 0001 — Start As A Modular Monolith

## Status

Accepted

## Context

The product may eventually operate multiple channels and multiple asynchronous capabilities, but the initial problem is validating a single end-to-end content generation pipeline.

Starting with microservices would introduce deployment, communication, observability, and operational complexity before the domain is understood.

## Decision

Implement `youtube-factory` as a modular monolith with explicit module boundaries.

## Consequences

Positive:

- faster development
- easier local execution
- simpler testing
- easier refactoring while the domain evolves

Negative:

- future extraction may require work if specific modules need independent scaling

This tradeoff is acceptable for the current stage.
