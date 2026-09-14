# AGENTS.md

## Project

`youtube-factory` is a software platform for generating, rendering, reviewing, publishing, and analyzing YouTube Shorts with a high degree of automation while preserving content quality and human approval before publication.

The first target use case is a single Spanish-language YouTube Shorts channel focused on engineering, technology, and everyday technical curiosities.

## Primary Objective

Build a reliable local vertical slice that transforms a topic into a publishable Short:

`topic -> research -> script -> scenes -> narration -> assets -> render -> final.mp4`

The first reference topic is:

> ¿Por qué las tapas de alcantarilla son redondas?

Do not implement YouTube publishing, n8n orchestration, multi-channel execution, or advanced analytics before the local vertical slice is working and reviewed.

## Core Engineering Principles

1. Prefer simple, explicit, testable code over clever abstractions.
2. Keep business logic in Python, never in n8n.
3. Treat LLM output as untrusted input and validate it with Pydantic models.
4. All external providers must be hidden behind interfaces or adapters.
5. Domain models must not depend on provider-specific SDK types.
6. Keep the first implementation local-first.
7. Preserve intermediate artifacts for debugging and reproducibility.
8. Human approval is required before publication during the initial phases.
9. Multi-channel support should influence architecture, but must not be over-engineered or implemented prematurely.
10. Every feature should be developed through small milestones with tests.

## Technology Baseline

- Python 3.12
- FastAPI for future internal HTTP APIs
- Pydantic v2 for contracts and validation
- pytest for tests
- ruff for linting/formatting
- mypy for static type checking
- FFmpeg for media rendering
- PostgreSQL + SQLAlchemy + Alembic in a later milestone
- Docker / Docker Compose for reproducible local execution
- n8n only as an external workflow orchestrator in a later milestone

## Architecture Rules

Use a modular architecture with clear boundaries between:

- domain models
- application services / use cases
- provider interfaces
- infrastructure adapters
- CLI / API entry points

Recommended package shape:

```text
src/youtube_factory/
├── domain/
├── application/
├── ports/
├── adapters/
├── cli/
└── api/
```

Provider abstractions should exist for capabilities such as:

- LLM generation
- research/search
- fact checking
- TTS
- image generation or image sourcing
- storage
- rendering
- YouTube publishing
- analytics

Do not bind domain code directly to OpenAI, ElevenLabs, YouTube, S3, or any other vendor.

## Initial Domain Contracts

At minimum, model these concepts explicitly:

- Topic
- ResearchResult
- Source
- Script
- ScenePlan
- Scene
- Narration
- Asset
- RenderJob
- RenderResult
- ShortProject

Prefer immutable or clearly validated models where practical.

## Output Artifact Contract

Each generated Short should have a dedicated working directory similar to:

```text
output/short_000001/
├── topic.json
├── research.json
├── script.json
├── scenes.json
├── narration.mp3
├── subtitles.ass
├── assets/
│   ├── scene_01.png
│   ├── scene_02.png
│   └── ...
└── final.mp4
```

Intermediate JSON artifacts are part of the product. Do not treat them as temporary implementation details.

## First Milestone Definition of Done

The first milestone is complete only when a command similar to:

```bash
python -m youtube_factory create \
  --topic "Por qué las tapas de alcantarilla son redondas"
```

produces a coherent vertical Short locally, including:

- validated topic data
- research output with sources
- structured script
- structured scene plan
- narration audio
- scene assets
- subtitles
- rendered 9:16 MP4

The result must be inspectable and understandable by a human.

## What Not To Build Yet

Do not implement the following unless a milestone explicitly requires it:

- autonomous YouTube publishing
- production deployment
- n8n workflows
- multi-channel execution
- recommendation algorithms
- advanced experiment engines
- dashboards
- complex event-driven infrastructure
- microservices
- Kubernetes

A modular monolith is the preferred starting point.

## Coding Standards

- Type all public functions.
- Use Pydantic models for external and LLM-derived structured data.
- Avoid raw dictionaries across application boundaries.
- Raise domain-specific exceptions where useful.
- Add tests for parsing, validation, transformations, and orchestration logic.
- External calls should be mockable.
- Avoid hidden global state.
- Use dependency injection through constructors or explicit parameters.

## Working Style For Codex

Before implementing a milestone:

1. Read `YOUTUBE_FACTORY_CONTEXT.md`.
2. Read relevant files under `docs/`.
3. Check existing ADRs before making architectural decisions.
4. Propose the smallest coherent change.
5. Implement it.
6. Add or update tests.
7. Run relevant tests, linting, and type checks.
8. Update documentation if behavior or architecture changed.

Do not silently introduce major dependencies or architectural patterns.

For significant architectural decisions, create an ADR under `docs/ADR/`.

## Source Of Truth Priority

When instructions conflict, use this order:

1. Explicit user instruction in the current Codex task
2. `AGENTS.md`
3. Accepted ADRs
4. `docs/ARCHITECTURE.md`
5. `docs/ROADMAP.md`
6. `YOUTUBE_FACTORY_CONTEXT.md`
7. Existing implementation details

## Current Status

The project is in bootstrap phase.

The immediate goal is to create the repository skeleton, domain contracts, local CLI entry point, and first vertical slice foundations without prematurely integrating every external service.
