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

Run the quality checks:

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy
```
