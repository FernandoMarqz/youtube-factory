# Architecture

## Architectural Style

Start as a modular monolith.

The application should preserve clean boundaries so capabilities can be replaced or split later if necessary.

## Logical Layers

```text
┌─────────────────────────────┐
│ CLI / API                   │
├─────────────────────────────┤
│ Application / Use Cases     │
├─────────────────────────────┤
│ Domain                      │
├─────────────────────────────┤
│ Ports                       │
├─────────────────────────────┤
│ Infrastructure Adapters     │
└─────────────────────────────┘
```

## Suggested Repository Structure

```text
src/youtube_factory/
├── domain/
│   ├── models/
│   ├── enums.py
│   └── exceptions.py
├── application/
│   ├── use_cases/
│   └── services/
├── ports/
│   ├── llm.py
│   ├── research.py
│   ├── tts.py
│   ├── visuals.py
│   ├── renderer.py
│   ├── storage.py
│   ├── publisher.py
│   └── analytics.py
├── adapters/
│   ├── local/
│   ├── openai/
│   └── ffmpeg/
├── cli/
└── api/
```

## Main Pipeline

```text
Topic
  ↓
ResearchUseCase
  ↓
ResearchResult
  ↓
ScriptGenerationUseCase
  ↓
Script
  ↓
ScenePlanningUseCase
  ↓
ScenePlan
  ↓
NarrationGenerationUseCase
  ↓
Narration
  ↓
AssetGenerationUseCase
  ↓
Asset[]
  ↓
SubtitleGeneration
  ↓
RenderShortUseCase
  ↓
RenderResult
```

## Local Content Engine Foundation

The first executable subset is deliberately limited to:

```text
CLI -> CreateContentUseCase -> ResearchProvider -> ScriptGenerator -> ScenePlanner
                                  |                    |                |
                           ResearchResult             Script         ScenePlan

              -> NarrationGenerator -> SceneTimingReconciler -> ProjectArtifactStore
                     |                        |                    |
                 Narration + WAV         TimedScenePlan        JSON + WAV artifacts
```

`CreateContentUseCase` owns orchestration. The CLI only assembles adapters and displays the result.
The domain does not import ports, adapters, YAML, or environment configuration.

Current ports are `ResearchProvider`, `ScriptGenerator`, `ScenePlanner`, and
`NarrationGenerator`, and `ProjectArtifactStore`. Their local implementations are
`LocalResearchProvider`, `LocalScriptGenerator`, `LocalScenePlanner`, `LocalNarrationGenerator`,
and `FileSystemArtifactStore`. They preserve deterministic fixture behavior for offline regression
testing. OpenAI adapters implement dynamic research, script and scene generation behind the same
ports without changing orchestration or domain contracts.

Running the local slice creates:

```text
data/projects/<project-id>/
├── topic.json
├── research.json
├── script.json
├── scenes.json
├── narration.json
├── narration.wav
├── timed-scenes.json
├── visual-prompts.json
├── visual-assets.json
├── assets/scene-XX.png
└── manifest.json
```

The artifact store serializes Pydantic models as UTF-8, indented and key-sorted JSON. The manifest
contains the stable capability-based pipeline version, selected channel, narration provider/model/
voice/duration, topic and generated files.

`ScenePlan` is a provider-independent audiovisual timeline. Each scene carries ordered sequence
numbers, continuous start/end timing, duration, narration segment, visual description, visual
intent, asset type, optional on-screen text and optional transition suggestion. The domain
validates that the timeline starts at zero, has no gaps or overlaps, and ends at the total duration.
Scene planning stays separate from visual generation so future TTS, visual assets, subtitles,
transitions and FFmpeg rendering can consume `scenes.json` without reinterpreting the script.

After audio exists, its measured duration is authoritative. `NarrationGenerator` returns one
complete narration track and metadata; Phase 3's local adapter generates a valid deterministic WAV
with the Python standard library only. `SceneTimingReconciler` transforms the estimated `ScenePlan`
into `TimedScenePlan` using proportional scaling. It preserves sequence and creative instructions,
but gives the last scene the exact measured audio end time. Both artifacts are retained: future TTS
adapters can replace proportional scaling with sentence/word timing while renderers consume only
`timed-scenes.json`.

## Channel configuration and narration composition

Configuration is kept out of the domain and split intentionally:

```text
.env                         secrets and machine-local infrastructure
config/channels/*.yaml       version-controlled channel/editorial preferences
data/projects/<project-id>/  generated runtime artifacts
```

`application.config.load_channel_config` uses `yaml.safe_load` and immutable Pydantic models to
load a specific channel. The CLI first loads `.env`, then the channel, and finally composes the
adapters explicitly. A CLI narration override wins over the channel provider only for that run.
No adapter reads YAML; the OpenAI adapter receives an explicit `OpenAITTSConfig` constructor value.

The `visuals` section selects a provider, optional model, aspect ratio, dimensions and style. A CLI
visual-provider override wins for one run. The `publishing` section remains a typed placeholder.

## Visual prompting and assets

Visual generation preserves three separate contracts:

```text
ScenePlan / TimedScenePlan   semantic storyboard and render timing
VisualPromptPlan             channel-aware generation instructions
VisualAssetManifest          provider-neutral PNG inventory and metadata
```

`DeterministicVisualPromptBuilder` consumes `TimedScenePlan` and immutable `ChannelConfig`. It adds
style, portrait composition, caption-safe regions and text/logo/watermark exclusions. Prompting is
therefore independently testable and replaceable; the OpenAI adapter never interprets scenes.

`VisualAssetProvider` accepts one `VisualPrompt` and returns bytes plus a `VisualAsset`. The local
adapter uses Pillow to produce deterministic, correctly sized PNG cards. The OpenAI adapter uses the
official SDK and base64 PNG responses, validates the decoded image, and reports actual dimensions.
Both adapters return bytes to `ProjectArtifactStore`; neither writes arbitrary filesystem paths.
Prompt SHA-256 hashes connect each asset to the exact provider input without claiming that paid image
generation itself is deterministic.

## Dynamic semantic scene planning

`ScenePlanner` remains the provider-neutral `Script -> ScenePlan` port. `LocalScenePlanner` preserves
the reference eight-scene fixture. `OpenAIScenePlanner` uses the Responses API Structured Outputs
surface with provider-private Pydantic DTOs; raw responses and SDK types never enter the domain.

The OpenAI adapter validates configured scene-count bounds, contiguous sequences and narration
segmentation. Joining segments and collapsing whitespace runs must exactly reproduce
`Script.full_narration`; content is never silently repaired. Relative duration estimates are scaled
with decimal arithmetic to the script's estimated total, producing a continuous provisional
`scenes.json`. ADR 0008 remains authoritative: narration media duration is applied later by
`SceneTimingReconciler` and persisted separately in `timed-scenes.json`.

Channel YAML selects planner provider/model and pacing constraints. A CLI override wins at the
composition root. Both local and OpenAI planners expose neutral provider/model/identifier metadata
for the manifest. `AssetType.ANIMATION` remains semantic intent for future rendering, not generated
video in the current static-asset pipeline.

## Source-backed research and grounded script generation

`ResearchProvider` and `ScriptGenerator` remain separate application boundaries. Their local
implementations retain the reference-topic fixtures. `OpenAIResearchProvider` uses Responses API
web search plus a provider-private Structured Output DTO. URLs in its structured result are accepted
only when the web-search call returned matching source evidence; source titles from that evidence
take precedence over generated titles. Pydantic then maps the concise result into `ResearchResult`.

`OpenAIScriptGenerator` receives `Topic` and the validated `ResearchResult`. It receives no web tool
and cannot trigger research. Its DTO contains semantic script components and one-based indices into
`ResearchResult.key_facts`; `Script.claims` therefore contains exact persisted facts rather than
new provider prose. The request also includes summary, uncertainties and source context, with a
strict instruction not to add facts. Sophisticated semantic entailment remains future work.

`full_narration` is assembled from hook, body and ending by the adapter, avoiding duplicated model
fields. A small application service estimates duration at 150 spoken words per minute and enforces
the channel's minimum and maximum. The channel selects research/script providers, models and source
limit; explicit CLI overrides win at composition time and no adapter reads YAML or environment
variables.

## OpenAI narration adapter

`NarrationGenerator` remains a provider-independent port. The composition root uses the selected
channel's narration settings to choose `LocalNarrationGenerator` or `OpenAINarrationGenerator`.
The latter receives its API key from environment configuration and its model, voice and delivery
instructions from the channel. SDK responses and credentials do not cross into the domain: the
adapter returns the same `GeneratedNarration` value used by the local adapter.

The persisted `Narration` records generic provider, model, voice and input-character metadata for
reproducibility and future cost telemetry. It contains neither API credentials nor raw SDK/API
responses. The existing WAV validator and `SceneTimingReconciler` remain unchanged consumers of
the provider-neutral result.

## Domain Model Direction

### Topic

Represents the content idea being produced.

Suggested fields:

- id
- title
- language
- category
- created_at

### Source

Represents a research source.

Suggested fields:

- title
- url
- publisher
- retrieved_at
- notes

### ResearchResult

Suggested fields:

- topic_id
- summary
- key_facts
- sources
- uncertainties

### Script

Suggested fields:

- hook
- body
- ending
- full_narration
- hook_type
- estimated_duration_seconds
- claims

### Scene

Suggested fields:

- sequence
- narration_segment
- visual_description
- duration_seconds
- asset_type
- on_screen_text

### ScenePlan

Contains ordered `Scene` objects.

### Narration

Suggested fields:

- file_path
- duration_seconds
- provider
- voice

### Asset

Suggested fields:

- scene_sequence
- file_path
- asset_type
- source_type
- metadata

### RenderResult

Suggested fields:

- output_path
- width
- height
- duration_seconds
- fps

## External Provider Ports

### LLMProvider

Responsibilities:

- structured generation
- no domain persistence

### ResearchProvider

Responsibilities:

- retrieve source material
- return source metadata

### TTSProvider

Responsibilities:

- transform narration text into audio

### VisualAssetProvider

Responsibilities:

- create or retrieve scene-level media assets

### Renderer

Responsibilities:

- combine narration, scenes, captions, transitions, and media into the final output

### StorageProvider

Initially local filesystem.

Future implementation may use S3-compatible storage.

## Intermediate Artifacts

All meaningful steps should serialize inspectable state.

```text
output/<short_id>/
├── topic.json
├── research.json
├── script.json
├── scenes.json
├── narration.mp3
├── subtitles.ass
├── assets/
└── final.mp4
```

## Error Handling

Failures should identify the pipeline stage and preserve previously generated artifacts.

Prefer retrying an individual stage over regenerating the entire project.

## Configuration

Configuration should eventually separate channel behavior from code.

Initial implementation may use a single configuration file.

Future example:

```text
config/channels/engineering-es.yaml
```

## Persistence

Do not introduce PostgreSQL in the first coding milestone unless required for a specific feature.

When persistence is added, SQLAlchemy + Alembic are preferred.

## Orchestration

n8n is external to the business logic.

It will call stable application entry points through CLI or HTTP APIs.

## Rendering

FFmpeg is the default render engine.

Rendering should support:

- 1080x1920
- 9:16
- timed narration
- ASS subtitles
- image animation
- transitions
- overlays
- optional audio bed

## Security

Never commit:

- provider API keys
- OAuth tokens
- YouTube credentials
- secrets

Use `.env` locally and provide `.env.example`.
