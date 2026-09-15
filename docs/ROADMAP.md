# Roadmap

## Phase 0 — Bootstrap

### Goal

Create a maintainable Python repository ready for iterative development.

### Deliverables

- Python 3.12 project
- `pyproject.toml`
- package structure
- CLI skeleton
- pytest
- ruff
- mypy
- `.env.example`
- Dockerfile / Docker Compose only if useful at this stage
- initial domain contracts

### Definition of Done

The project installs locally, tests run, linting succeeds, and a basic CLI command executes.

Status: complete.

---

## Phase 1 — Local Vertical Slice

### Goal

Generate one complete Short from one manually supplied topic.

### Reference Topic

> ¿Por qué las tapas de alcantarilla son redondas?

### Deliverables

- Topic model
- ResearchResult model
- Script model
- ScenePlan model
- Narration model
- Asset model
- RenderResult model
- pipeline orchestration
- local artifact directory
- final MP4

### Definition of Done

A single CLI command produces all intermediate artifacts plus a valid vertical MP4.

### Current Phase 1 Scope

The content-engine foundation is complete for the local deterministic subset:

```text
Topic -> ResearchResult -> Script -> ScenePlan -> Narration -> TimedScenePlan
```

`create-content` writes `topic.json`, `research.json`, `script.json`, `scenes.json`, `narration.json`,
`narration.wav`, `timed-scenes.json`, and `manifest.json` under
`data/projects/<project-id>/`. The current providers support only the reference manhole-cover
topic and exist to validate ports, contracts, orchestration and reproducible persistence before
external AI or research integrations. The deterministic scene plan contains a continuous,
eight-scene, 34-second audiovisual timeline. The deterministic local WAV is measurable at 36.72
seconds, and the separate timed plan reconciles scene boundaries to that authoritative media
duration. Channel/editorial settings now live in typed `config/channels/*.yaml`, while `.env` is
limited to secrets and machine-local infrastructure. Assets, subtitles and rendering remain future
work; therefore this subset does not yet satisfy the full Phase 1 vertical-MP4 definition of done.

---

## Phase 2 — Research And Script Quality

### Goal

Improve factual quality and narrative consistency.

### Deliverables

- source-aware research
- structured claims
- fact-check stage
- hook variations
- duration estimation
- validation and retry policies

---

## Phase 3 — Media Engine

### Goal

Produce reusable narration and visual assets.

### Deliverables

- TTS abstraction
- first TTS adapter
- visual asset abstraction
- first visual adapter
- reusable asset metadata
- audio duration extraction
- typed channel configuration foundation for narration and future visuals

---

## Phase 4 — Visual Prompt And Asset Foundation

### Goal

Produce one validated provider-neutral visual prompt and PNG asset per timed scene.

### Deliverables

- `VisualPromptPlan`
- `VisualAssetManifest`
- deterministic prompt builder
- local placeholder provider
- OpenAI Images provider
- prompt hashes and manifest metadata

Status: complete.

### Phase 4B extension

Dynamic semantic scene planning is available through `OpenAIScenePlanner` using structured model
output, strict narration reconstruction and deterministic estimated-duration normalization. The
local fixture planner remains the offline default, and real narration remains authoritative for
`TimedScenePlan`.

---

## Phase 5 — Renderer

### Goal

Produce Shorts with consistent visual quality.

### Deliverables

- FFmpeg adapter
- 1080x1920 output
- subtitles
- scene timing
- zoom/pan
- transitions
- text overlays
- render validation

---

## Phase 6 — Persistence

### Goal

Persist projects and generation metadata.

### Deliverables

- PostgreSQL
- SQLAlchemy
- Alembic
- entities for Shorts and artifacts
- execution status model

Potential statuses:

```text
DRAFT
GENERATING
RENDERED
REVIEW_PENDING
APPROVED
SCHEDULED
PUBLISHED
FAILED
```

---

## Phase 7 — Internal API And n8n

### Goal

Expose stable orchestration endpoints.

### Deliverables

- FastAPI application
- generation endpoints
- project status endpoints
- approval endpoint
- n8n workflow

### Rule

n8n must orchestrate only. Business logic stays in Python.

---

## Phase 8 — YouTube Publishing

### Goal

Publish approved content through YouTube APIs.

### Deliverables

- YouTube publisher port
- OAuth integration
- upload adapter
- metadata generation
- scheduled publication
- human approval requirement

---

## Phase 9 — Analytics

### Goal

Collect content performance metrics.

### Deliverables

- YouTube Analytics adapter
- analytics snapshots
- scheduled ingestion
- normalized metrics

Suggested snapshots:

- 1h
- 6h
- 24h
- 72h
- 7d
- 30d

---

## Phase 10 — Experiment Engine

### Goal

Understand which content attributes correlate with performance.

### Candidate Variables

- hook type
- topic category
- duration
- scene count
- words per second
- voice
- visual style
- upload hour
- CTA

### Deliverables

- experiment metadata
- comparison queries
- simple scoring logic
- recommendations for future content experiments

---

## Phase 11 — Multi-Channel

### Goal

Reuse the same engine across multiple channels.

### Deliverables

- channel configuration model
- config-driven prompts/styles
- isolated credentials
- isolated analytics
- language variants

### Constraint

Do not start this phase until the first channel has demonstrated a repeatable content format.
