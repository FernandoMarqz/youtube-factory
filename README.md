# youtube-factory

AI-assisted platform for generating, rendering, reviewing, publishing, and analyzing YouTube Shorts.

## Current stage

Phase 5: provider-neutral FFmpeg rendering of persisted media. Rendering requires `ffmpeg` and
`ffprobe` on PATH; the project does not download or bundle them.

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

Create the deterministic offline Short for the current reference topic:

```powershell
python -m youtube_factory create-content `
  --topic "¿Por qué las tapas de alcantarilla son redondas?" `
  --narration-provider local `
  --renderer ffmpeg
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
├── render.json
├── render/short.mp4
└── manifest.json
```

Use `--output-dir <path>` to choose another root. The project identifier and local-provider JSON
content are stable for the same input. The local research, script and scene-planning adapters remain
intentional deterministic fixtures for the reference topic. OpenAI-backed implementations can now
handle arbitrary topics while the local fixtures preserve offline regression coverage. Rendering is
available in Phase 5; databases and publishing are not implemented yet.

`scenes.json` is a deterministic audiovisual timeline. Each scene has a narration segment,
continuous start/end/duration estimates, a separate visual instruction and purpose, an asset type,
and optional on-screen text or transition suggestion. It is planning data only: future TTS, visual
assets consume it without changing its creative intent. Rendering uses `timed-scenes.json`, whose
boundaries come from the measured narration WAV, rather than the provisional `scenes.json` timings.

## Phase 5: render a vertical MP4

Offline end-to-end generation (the local narration is a silent timing fixture):

```powershell
python -m youtube_factory create-content `
  --channel engineering-es `
  --topic "¿Por qué las tapas de alcantarilla son redondas?" `
  --research-provider local `
  --script-generator local `
  --scene-planner local `
  --narration-provider local `
  --visual-provider local-placeholder `
  --renderer ffmpeg
```

To render existing media, including previously paid narration and images, without invoking any
research, script, scene, TTS or image provider:

```powershell
python -m youtube_factory render-project `
  --project-id <project-id> `
  --channel engineering-es `
  --renderer ffmpeg
```

Use `--output-dir <path>` on either command if the project is outside `data/projects`.
The renderer uses one persisted PNG per timed scene. It scales each image proportionally to cover
1080x1920 and crops the overflow symmetrically. Hard cuts join the static scenes; the persisted
WAV becomes the AAC audio track. The target is 30 fps H.264/yuv420p in MP4. No captions,
animation, transitions or music are rendered yet. The final file is `render/short.mp4` and its
ffprobe-measured metadata is in `render.json`. `manifest.json` lists both and identifies the
renderer. Duration may differ from the WAV by at most two video frames (frame and AAC rounding).

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

## Phase 4B: AI scene planning

Scene planning now has two implementations behind the unchanged provider-neutral `ScenePlanner`
port:

- `LocalScenePlanner` is the fixed eight-scene adapter for offline regression work.
- `OpenAIScenePlanner` uses OpenAI Responses Structured Outputs for arbitrary validated `Script`
  values.

The channel defaults to local planning. An explicit `--scene-planner` overrides the channel for one
run; no automatic fallback occurs. OpenAI output is first validated against a provider-private
Pydantic schema, then checked for contiguous sequence, configured scene count and exact narration
reconstruction. Reconstruction ignores only whitespace-run differences; changed punctuation,
invented words, omissions, repetitions and reordering fail the stage.

AI duration values are relative estimates. They are deterministically normalized to
`Script.estimated_duration_seconds` for `scenes.json`. After narration exists, the unchanged
`SceneTimingReconciler` makes `timed-scenes.json` end at the measured WAV duration. `ANIMATION`
continues to mean creative motion intent only; Phase 4 still creates one static PNG per scene.

Local planner execution:

```powershell
python -m youtube_factory create-content `
  --channel engineering-es `
  --topic "¿Por qué las tapas de alcantarilla son redondas?" `
  --scene-planner local `
  --narration-provider local `
  --visual-provider local-placeholder
```

Paid planner-only smoke test for the currently supported upstream reference topic:

```powershell
python -m youtube_factory create-content `
  --channel engineering-es `
  --topic "¿Por qué las tapas de alcantarilla son redondas?" `
  --scene-planner openai `
  --narration-provider local `
  --visual-provider local-placeholder
```

Only scene planning is expected to use paid API capacity in that command.

## Phase 4C: source-backed research and grounded scripts

Research and script generation now each have local and OpenAI implementations behind their existing
provider-neutral ports:

```text
Topic -> OpenAIResearchProvider -> ResearchResult
ResearchResult -> OpenAIScriptGenerator -> Script
```

`OpenAIResearchProvider` uses the Responses API web-search tool and Structured Outputs. It requires
at least one source, rejects duplicate or invalid URLs, and verifies every persisted URL against
source evidence returned by the web-search call. It stores summary, facts, sources and uncertainties
in `research.json`; raw pages and SDK responses are not persisted.

`OpenAIScriptGenerator` receives that validated artifact and has no web tool. Its instructions allow
only supplied research facts. Structured output contains hook, body, ending, hook type and selected
fact indices. Python constructs `full_narration`, copies the referenced research facts into
`Script.claims`, and estimates duration deterministically at 150 spoken words per minute. Scripts
outside the channel's configured Short-duration bounds receive at most one grounded OpenAI
rewrite. Python recalculates the duration and rejects a second out-of-range result before
downstream stages. The configured content target/min/max values drive both requests; only the
accepted script is persisted.

Provider precedence for research, script, scene planning, narration and visuals is:

```text
explicit CLI override > selected channel YAML > no fallback
```

Preferred Phase 4C paid smoke test, using local narration and visuals:

```powershell
python -m youtube_factory create-content `
  --channel engineering-es `
  --topic "¿Por qué los puentes tienen juntas de dilatación?" `
  --research-provider openai `
  --script-generator openai `
  --scene-planner openai `
  --narration-provider local `
  --visual-provider local-placeholder `
  --renderer ffmpeg
```

This intentionally pays only for web-backed research, script generation and scene planning. A full
AI command changes the final two providers to `openai`; it additionally incurs one TTS request and
approximately one paid image request per generated scene. Paid commands are manual and never run by
pytest.

Full AI creative pipeline:

```powershell
python -m youtube_factory create-content `
  --channel engineering-es `
  --topic "¿Por qué los puentes tienen juntas de dilatación?" `
  --research-provider openai `
  --script-generator openai `
  --scene-planner openai `
  --narration-provider openai `
  --visual-provider openai `
  --renderer ffmpeg
```

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
