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

`CreateContentUseCase` owns orchestration. The CLI only assembles local adapters and displays
the result. The domain does not import ports or adapters.

Current ports are `ResearchProvider`, `ScriptGenerator`, `ScenePlanner`, and
`NarrationGenerator`, and `ProjectArtifactStore`. Their local implementations are
`LocalResearchProvider`, `LocalScriptGenerator`, `LocalScenePlanner`, `LocalNarrationGenerator`,
and `FileSystemArtifactStore`. The first four are deterministic, fixture-like adapters for the
reference topic; they make contracts, artifact
persistence, and reproducibility testable before they are replaced by AI-backed or source-backed
implementations.

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
└── manifest.json
```

The artifact store serializes Pydantic models as UTF-8, indented and key-sorted JSON. The
manifest contains the stable pipeline version, provider identifiers, topic and generated files.
No network request is performed in this phase.

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
