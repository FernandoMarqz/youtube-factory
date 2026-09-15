# youtube-factory

AI-assisted platform for generating, rendering, reviewing, publishing, and analyzing YouTube Shorts.

## Current stage

Bootstrap / MVP architecture.

The immediate target is a local vertical slice:

```text
topic -> research -> script -> scenes -> narration -> assets -> render -> final.mp4
```

Reference topic:

> ¿Por qué las tapas de alcantarilla son redondas?

## Start here

Codex and contributors should read:

1. `AGENTS.md`
2. `YOUTUBE_FACTORY_CONTEXT.md`
3. `docs/PRODUCT.md`
4. `docs/ARCHITECTURE.md`
5. `docs/ROADMAP.md`
6. `docs/ADR/`

## Initial stack

- Python 3.12
- Pydantic v2
- FastAPI later
- pytest
- ruff
- mypy
- FFmpeg
- Docker / Docker Compose

PostgreSQL, n8n, YouTube APIs, and analytics will be added only after the local media pipeline is working.

## Bootstrap commands

Create a Python 3.12 virtual environment and install the development dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Confirm the bootstrap CLI is available:

```powershell
python -m youtube_factory status
```

## Phase 1: local content engine

Create deterministic research and a Short script for the current reference topic:

```powershell
python -m youtube_factory create-content `
  --topic "¿Por qué las tapas de alcantarilla son redondas?"
```

The command prints its project directory and writes these inspectable artifacts:

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

Use `--output-dir <path>` to choose another root. The project identifier and JSON content are
stable for the same input. The local research, script and scene-planning adapters are intentional
deterministic fixtures: they validate the pipeline offline before they are replaced by AI-backed
adapters. They support only the reference topic. No web search, HTTP API, LLM-backed planner,
narration, media generation, renderer, database or publishing integration exists yet.

`scenes.json` is a deterministic audiovisual timeline. Each scene has a narration segment,
continuous start/end/duration estimates, a separate visual instruction and purpose, an asset type,
and optional on-screen text or transition suggestion. It is planning data only: future TTS, visual
assets, subtitles, transitions and rendering consume it without changing its creative intent.

## Phase 4: visual prompts and assets

`TimedScenePlan` now feeds two explicit provider-neutral stages:

```text
Scene.visual_description   semantic creative intent
VisualPromptPlan           channel-aware, generation-ready instructions
VisualAssetManifest        persisted PNG locations and traceability metadata
```

The deterministic prompt builder adds the selected channel's style, portrait/mobile composition,
caption-safe space and exclusions for generated captions, logos, watermarks and UI. It does not
simply forward `visual_description`, and its output is independently inspectable in
`visual-prompts.json`.

The default `local-placeholder` visual provider creates one real 1024x1536 PNG card per scene. It
is deterministic, offline and needs no API key. An explicit OpenAI visual override uses the channel
model (`gpt-image-2`) and the official Images API:

```powershell
python -m youtube_factory create-content `
  --channel engineering-es `
  --topic "¿Por qué las tapas de alcantarilla son redondas?" `
  --narration-provider local `
  --visual-provider openai
```

This manual smoke test makes one paid image request per scene (currently eight). It is never run by
the automated test suite. The configured 1024x1536 portrait size maps directly to OpenAI's supported
1024x1536 size; other dimensions map to the nearest supported square, landscape or portrait aspect
without resizing or falsely reporting dimensions. `visual-assets.json` records the actual decoded
PNG dimensions and a SHA-256 hash of the exact prompt sent.

Provider precedence is the same for narration and visuals: an explicit CLI override wins over the
selected channel YAML, and there is no implicit provider fallback. The safe channel default remains
`local-placeholder` for visuals even though its OpenAI model is retained for an intentional CLI
override.

## Phase 3: narration and timing

The local pipeline now creates one deterministic, valid mono PCM/WAV narration track at 16 kHz.
It is intentionally silent and is not synthetic speech. Its purpose is to validate the
provider-independent `NarrationGenerator` port, binary-artifact persistence and audio inspection
without an external TTS provider.

`scenes.json` remains the creative, estimated storyboard. `timed-scenes.json` is a separate
render-ready `TimedScenePlan`: its timeline is scaled proportionally to the measured WAV duration,
starts at zero and ends exactly at that duration. This is an initial strategy; real TTS providers
will later supply sentence or word timestamps for more precise reconciliation.

## Narration providers

Configuration has three distinct responsibilities:

```text
.env                         = secrets and machine-local infrastructure
config/channels/*.yaml       = editorial and generation preferences
data/projects/<project-id>/  = generated runtime artifacts
```

Copy `.env.example` to ignored `.env` and set only machine-local values such as
`OPENAI_API_KEY` or `YOUTUBE_FACTORY_OUTPUT_DIR`. Channel voice, model, language, duration and
future visual preferences live in version-controlled YAML, never in `.env`.

`engineering-es` is the default channel and currently selects OpenAI narration. Use the local
override for deterministic, offline and zero-cost development:

```powershell
python -m youtube_factory create-content `
  --channel engineering-es `
  --topic "¿Por qué las tapas de alcantarilla son redondas?" `
  --narration-provider local
```

For a real OpenAI run, omit the override so the selected channel supplies the configured model,
voice and instructions:

```powershell
python -m youtube_factory create-content `
  --channel engineering-es `
  --topic "¿Por qué las tapas de alcantarilla son redondas?"
```

An explicit `--narration-provider` takes precedence over the channel provider for that invocation;
otherwise the channel is the source of truth. `create-content` loads only `.env` from its working
directory, and real process environment variables take precedence. It never loads `.env.example`.
The manifest records the selected channel and provider/model/voice/duration without copying secrets
or the full channel file.

In PowerShell, this prompts for the key instead of placing it in shell history:

```powershell
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", (Read-Host -AsSecureString "OpenAI API key")).Password
```

Run the quality checks:

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy
```
