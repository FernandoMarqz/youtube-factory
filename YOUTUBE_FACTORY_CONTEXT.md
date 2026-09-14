# YouTube Factory — Project Context

## 1. Vision

The goal is to build a reusable software platform capable of creating and operating YouTube Shorts channels with a high degree of automation.

The platform should eventually support:

- topic discovery
- research
- script generation
- fact checking
- scene planning
- narration generation
- image/video asset creation or sourcing
- automatic rendering
- human review
- YouTube publishing
- analytics ingestion
- experiment tracking
- learning from content performance
- multiple channels driven mainly by configuration

The first objective is not to build a large network of automated channels. The first objective is to prove that a single content format can be produced reliably and perform well enough to justify scaling.

## 2. Business Hypothesis

The broader business idea is to create semi-automated or heavily automated YouTube channels whose content production pipeline is powered by AI and software automation.

The preferred business strategy is not to depend exclusively on Shorts ad revenue. In the long term, the platform should allow channels to support multiple monetization paths such as:

- YouTube advertising
- long-form content
- affiliate revenue
- sponsorships
- digital products
- newsletters
- audience-driven products or services

The first technical milestone is independent from monetization.

## 3. Initial Channel Concept

The first test channel will be in Spanish and focus on:

- engineering curiosities
- technology
- infrastructure
- everyday objects with interesting technical explanations
- science-adjacent practical explanations

Example topics:

- Why manhole covers are round
- Why airplane windows have a small hole
- Why high-voltage cables have colored balls
- Why airplanes appear not to fly in straight lines
- Why windshields have black dots around their edges

The content should be evergreen where possible.

## 4. Content Philosophy

The goal is not to produce generic mass-generated AI content.

Each Short should provide genuine informational value and should have:

- a strong hook
- a clear narrative
- a distinct explanation
- factual grounding
- visual variety
- original editing
- captions
- coherent pacing

The system should optimize quality and repeatability before scale.

## 5. First Functional Goal

Build one local end-to-end pipeline:

```text
topic
  -> research
  -> script
  -> scene planning
  -> narration
  -> assets
  -> subtitles
  -> FFmpeg render
  -> final.mp4
```

Reference topic:

> ¿Por qué las tapas de alcantarilla son redondas?

The first milestone should produce a final Short that is good enough to be manually reviewed for publication.

## 6. Technology Decisions

Initial stack:

- Python 3.12
- FastAPI later for internal APIs
- Pydantic v2
- pytest
- ruff
- mypy
- FFmpeg
- Docker / Docker Compose

Later milestones:

- PostgreSQL
- SQLAlchemy
- Alembic
- n8n
- YouTube Data API
- YouTube Analytics API

## 7. Why Python

Python is preferred over Java for this project because the initial workload is heavily oriented toward:

- AI integrations
- audio processing
- media manipulation
- automation
- rapid experimentation
- data analysis

The architecture should still follow disciplined software engineering practices.

## 8. Why n8n Is Not The Core Application

n8n may be introduced later as an orchestration layer.

Its responsibilities may include:

- scheduling
- triggering generation jobs
- sending approval notifications
- reacting to human approval
- invoking publishing jobs
- triggering analytics collection

It must not contain core business logic.

Bad pattern:

```text
n8n
 -> prompts
 -> large JavaScript nodes
 -> SQL
 -> provider logic
 -> rendering rules
```

Preferred pattern:

```text
n8n
 -> call youtube-factory API / CLI
 -> wait for result
 -> request human approval
 -> trigger next application use case
```

## 9. Architecture Direction

Start as a modular monolith.

Suggested modules:

```text
domain
application
ports
adapters
cli
api
```

The domain should not depend on external providers.

Application services orchestrate domain behavior and provider ports.

Adapters implement specific providers.

Example abstractions:

```text
LLMProvider
ResearchProvider
TTSProvider
VisualAssetProvider
Renderer
StorageProvider
Publisher
AnalyticsProvider
```

## 10. Provider Strategy

Do not hardcode business logic around one vendor.

Possible providers may change over time:

LLM:
- OpenAI
- other hosted models
- local models

TTS:
- OpenAI
- ElevenLabs
- local TTS

Visuals:
- generated images
- licensed stock/media APIs
- diagrams created programmatically
- future video generation

Storage:
- local filesystem first
- S3/compatible storage later

## 11. Structured LLM Output

LLM output must be validated.

Do not pass large free-form text blobs between pipeline stages when structured contracts are possible.

Example concepts:

```text
Topic
ResearchResult
Script
ScenePlan
Scene
Narration
Asset
RenderResult
```

Prefer JSON/Pydantic contracts.

Example concept:

```python
class Script(BaseModel):
    topic: str
    hook: str
    narration: str
    hook_type: HookType
    estimated_duration_seconds: float
    sources: list[Source]
```

## 12. Artifact-First Pipeline

Each step should write inspectable artifacts.

Example:

```text
output/short_000001/
├── topic.json
├── research.json
├── script.json
├── scenes.json
├── narration.mp3
├── subtitles.ass
├── assets/
└── final.mp4
```

Benefits:

- reproducibility
- debugging
- manual review
- partial regeneration
- experiment comparison
- provider migration

## 13. Rendering Strategy

The first version should avoid expensive full-video generation.

The initial visual strategy should combine:

- generated or sourced still images
- diagrams
- zoom and pan
- crop animation
- transitions
- overlays
- captions
- arrows/highlights
- optional background music
- sound effects where appropriate

FFmpeg is the primary renderer.

Target output:

- 9:16
- 1080x1920
- Short-form duration
- coherent caption timing
- mobile-first readability

## 14. Human In The Loop

The initial system must not publish blindly.

Expected flow:

```text
generate
 -> render
 -> automated QA
 -> human review
 -> approve / regenerate / reject
 -> publish
```

Human approval can later be delivered through a web interface, Telegram, or another channel.

## 15. Persistence Strategy

PostgreSQL is intentionally deferred until the media pipeline works.

When introduced, persist concepts such as:

- Channel
- Short
- Topic
- Script
- Scene
- Asset
- Render
- Publication
- AnalyticsSnapshot
- Experiment metadata

## 16. Analytics Vision

Eventually ingest YouTube performance metrics for every Short.

Potential metrics:

- views
- engaged views
- average view duration
- average percentage viewed
- likes
- comments
- shares
- subscribers gained

Collect snapshots at useful time intervals such as:

- 1 hour
- 6 hours
- 24 hours
- 72 hours
- 7 days
- 30 days

The platform should later correlate content attributes with performance.

## 17. Experiment Engine Vision

Each Short may eventually contain experiment metadata such as:

- topic category
- hook type
- duration
- number of scenes
- words per second
- voice
- visual style
- CTA
- upload time

The system should make it possible to answer questions like:

> Which hook types achieve the highest average percentage viewed?

or:

> Do Shorts between 28 and 34 seconds perform better than longer ones?

This is a later milestone, not an MVP requirement.

## 18. Multi-Channel Vision

The long-term system should allow channels to be mostly config-driven.

Example future configuration:

```yaml
channel:
  id: engineering_es
  language: es

content:
  niche: engineering_curiosities
  target_duration_seconds: 35

visuals:
  aspect_ratio: "9:16"
  style: educational

publishing:
  shorts_per_day: 2
```

The architecture should make this possible later, but the first implementation must focus on one channel.

## 19. Explicit Non-Goals For The First Milestone

Do not build yet:

- multiple channels
- production-grade distributed architecture
- Kubernetes
- queues unless clearly needed
- event buses
- recommendation engines
- autonomous publication
- advanced dashboards
- automatic monetization logic
- large n8n workflows

## 20. Development Strategy

Build through milestones:

1. repository bootstrap
2. domain contracts
3. local CLI
4. research + script vertical slice
5. scene planning
6. narration
7. media assets
8. subtitles
9. FFmpeg rendering
10. review quality
11. persistence
12. n8n orchestration
13. YouTube publishing
14. analytics
15. experiments
16. multi-channel scaling

Each milestone should leave the codebase working.

## 21. Quality Bar

The system succeeds technically when:

- pipeline steps are isolated and testable
- output contracts are validated
- intermediate state is inspectable
- providers are replaceable
- generation is reproducible enough to debug
- one command can eventually produce a complete Short

The system succeeds as a product only when the generated content is genuinely worth publishing.
