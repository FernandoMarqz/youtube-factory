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

Run the quality checks:

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy
```
