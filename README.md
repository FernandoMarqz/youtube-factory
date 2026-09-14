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
assets, subtitles, transitions and rendering will consume it, but this command creates no media.

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

Local narration remains the default, so development and tests are deterministic, offline and
zero-cost:

```powershell
python -m youtube_factory create-content `
  --topic "¿Por qué las tapas de alcantarilla son redondas?" `
  --narration-provider local
```

An intentional OpenAI smoke test can generate real Spanish speech through the same
`NarrationGenerator` port. Set `OPENAI_API_KEY` in the shell that invokes the command (and never
commit it); `.env.example` documents the available variables. Then run:

```powershell
python -m youtube_factory create-content `
  --topic "¿Por qué las tapas de alcantarilla son redondas?" `
  --narration-provider openai
```

`OPENAI_TTS_MODEL` defaults to `gpt-4o-mini-tts`, `OPENAI_TTS_VOICE` defaults to `cedar`, and
`OPENAI_TTS_INSTRUCTIONS` controls the Spanish delivery style. The OpenAI adapter requests WAV,
measures the returned audio, persists provider-neutral metadata in `narration.json`, and keeps
`scenes.json` separate from the audio-authoritative `timed-scenes.json`. No API call is made by
the default command or the automated test suite.

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
