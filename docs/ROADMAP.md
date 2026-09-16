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
limited to secrets and machine-local infrastructure. The later Phase 4 visual and Phase 5 render
work now satisfy the media portion of the local vertical slice; subtitles and human review remain.

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

### Phase 4C extension

Source-backed arbitrary-topic research and grounded script generation are available through
`OpenAIResearchProvider` and `OpenAIScriptGenerator`. Research uses Responses API web search,
persists verified source metadata and remains separate from script generation. Scripts consume only
the validated `ResearchResult`; full narration and duration are derived deterministically. Local
reference fixtures remain the offline defaults.

---

## Phase 5 — Renderer

### Goal

Produce a correct first vertical MP4 from persisted narration, timed scenes and PNGs.

### Deliverables

- FFmpeg adapter
- 1080x1920 output
- authoritative narration-derived scene timing
- static scenes with hard cuts and aspect-preserving cover/crop
- render-only command for existing media
- render validation

Status: complete. A full offline MP4 and the render-only command were verified with FFmpeg/ffprobe;
the complete automated suite passed with the tools on PATH. Subtitles, motion, transitions and
overlays are deferred.

---

## Phase 6 - Subtitle And Caption Foundation

Status: complete. Real WAV word timestamps from OpenAI (`whisper-1` verbose JSON) are reconciled
against canonical narration; local synthetic alignment supports offline work. Deterministic
caption chunks, `captions.json`, ASS styling and FFmpeg/libass burn-in are implemented.
`caption-project` aligns saved narration only; `render-project` restyles and rerenders saved media.
Human review remains required before any future publication.

## Phase 6B - Dynamic Word Emphasis

Status: complete. Explicit cue word ranges and validated legacy sequential mapping reuse
`word-alignment.json`; deterministic ASS events change only active-word color without text
reflow. `render-project` regenerates ASS and MP4 offline from persisted captions and media.
Static Phase 6 captions remain available by disabling emphasis. No new AI call is involved.

## Phase 7 - Deterministic Audio Polish

Status: complete. FFmpeg measures narration loudness, applies two-pass normalization, optionally
mixes an explicitly supplied local music file with looping, gain and fades, and ducks music from
the narration sidechain. A final limiter and encoded-file LUFS/true-peak validation protect speech
clarity. `audio-mix.json` and manifest metadata are persisted; `render-project` applies changes
without upstream calls. Music is disabled by default and licensing remains the user's decision.

Next: Phase 8, subtle deterministic scene motion and hard-cut polish without changing scene timing.

---

## Later Phase - Persistence

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

## Later Phase - Internal API And n8n

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

## Later Phase - YouTube Publishing

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
