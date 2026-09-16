# YouTube Factory - Fresh-Session Handoff

## Purpose And Status

Build a local-first, inspectable pipeline for a Spanish engineering/technology YouTube Shorts
channel. Human approval is required before any future publication. Python 3.12, Pydantic v2,
pytest, ruff and mypy are the current baseline. The architecture is a modular monolith with
domain contracts, application use cases/services, provider ports, infrastructure adapters and a
CLI composition root. PostgreSQL, FastAPI, n8n, publishing and analytics are deferred.

Phase 6 adds canonical-text captions, local synthetic and OpenAI acoustic word alignment,
deterministic cue planning and FFmpeg/libass burn-in. Phase 5 was verified with a real MP4. FFmpeg
9.0.1 was already installed on the development machine through winget, but its bin directory was
missing from the shell's
PATH. A temporary PATH addition allowed the full offline render and test suite to pass. No
machine-specific FFmpeg path is stored in project code or channel configuration.

## Implemented Pipeline And Providers

```text
Topic -> ResearchResult -> Script -> ScenePlan -> Narration + WAV
      -> TimedScenePlan -> VisualPromptPlan -> VisualAssetManifest
      -> CaptionAlignmentProvider -> WordAlignment -> CaptionPlanner -> CaptionPlan
      -> ASS -> Renderer -> RenderArtifact
```

`ResearchProvider`, `ScriptGenerator`, `ScenePlanner`, `NarrationGenerator`, and
`VisualAssetProvider` each have deterministic local and OpenAI adapters. Local research/script/
scene planning are reference-topic fixtures. Local narration is silent mono PCM WAV for offline
timing tests; OpenAI TTS output is normalized to mono 16-bit PCM WAV before persistence. Local
visuals are deterministic PNG cards; OpenAI visuals are real generated PNGs. `Renderer` currently
has `FFmpegRenderer`. `CaptionAlignmentProvider` has local synthetic and OpenAI (`whisper-1`)
adapters. `ProjectArtifactStore` has a filesystem adapter.

OpenAI research uses web search and only persists URLs present in tool source evidence. Script
generation consumes validated research without its own search; it references exact research facts,
and Python builds full narration and estimates duration. AI scene planning validates complete
narration reconstruction and uses model durations only as relative weights. These decisions are
recorded in ADRs 0011 and 0012.

`OpenAIScriptGenerator` targets the channel content duration and performs at most one automatic
rewrite when its deterministic 150-words-per-minute estimate is outside min/max bounds. The
rewrite receives the original script and the same `ResearchResult`; only a duration-valid final
script is returned and persisted. The local script fixture remains unchanged.

## Timing, Visuals And Rendering

`scenes.json` is a semantic/provisional timeline. `narration.wav` is measured audio.
`timed-scenes.json` reconciles scene boundaries to that audio and is the sole authoritative render
timeline. Visual prompts are built separately from scene descriptions, then
`visual-assets.json` maps one persisted PNG per scene with its exact prompt hash. `ANIMATION`
is editorial intent only.

The renderer reads persisted WAV and PNGs; it never regenerates them. It uses static scenes with
hard cuts. Images scale proportionally to cover 1080x1920 and are center-cropped without source
modification. Output is 30 fps H.264/AAC/yuv420p MP4 according to typed channel configuration.
`ffprobe` checks streams, codecs, size, FPS and duration within two frames of the timed narration.
FFmpeg executables are discovered through PATH, with no bundled binary or hardcoded machine path.
ASS caption chunks can be burned in after scene concatenation without changing audio mapping.
No music, motion, per-word highlighting or publishing are implemented.

## Configuration And Artifacts

`.env` contains only secrets and machine-local output root. Version-controlled
`config/channels/engineering-es.yaml` has typed immutable research, script, scene planning,
narration, visuals, render, captions and publishing sections. CLI override wins over channel
settings; there
is no implicit fallback. The channel defaults to local research/script/planning/visuals, OpenAI
narration, and FFmpeg rendering. Use the local narration override for an offline run.

Each project is under `data/projects/<project-id>/` by default, unless `.env` or `--output-dir`
overrides the root. It contains `topic.json`,
`research.json`, `script.json`, `scenes.json`, `narration.json`, `narration.wav`,
`timed-scenes.json`, `visual-prompts.json`, `visual-assets.json`, `assets/scene-XX.png`,
`word-alignment.json`, `captions.json`, `captions/captions.ass`, `render.json`, `render/short.mp4`
and `manifest.json`. The manifest inventories artifacts and provider identities, including the
renderer. Intermediate files are product artifacts, not temp
files. The render-only use case validates stored media before rendering; it makes no upstream
provider calls.

Caption text comes from persisted `narration.narration_text`; transcription supplies only timing
from the actual WAV. OpenAI uses the documented Python `audio.transcriptions.create` with
`whisper-1`, `verbose_json`, word granularity and a Spanish language hint. Ordered normalized
matching tolerates punctuation, case and accents while preserving canonical display text. Below
90% matched canonical tokens, alignment fails. Local timing is explicitly synthetic. The OpenAI
adapter repairs isolated zero-length word intervals using no more than 20 ms of neighboring time;
fully degenerate and non-monotonic responses still fail. The planner
groups roughly 2-5 words with punctuation/duration limits and at most two lines, checking the
actual line break as it groups. ASS uses bold white Arial 64, dark outline, small shadow and
450px bottom margin. The fixed relative libass
path is resolved from the project working directory to avoid Windows filter escaping.
The Phase 6 offline CLI smoke test produced a captioned 1080x1920, 30 fps H.264/AAC/yuv420p
MP4 at 36.733333 seconds. A frame was visually checked for readable two-line safe-area text.
With FFmpeg on PATH, all 184 tests passed; ruff, mypy and `git diff --check` passed. No paid
caption alignment call was made during implementation.

## Commands

```powershell
python -m youtube_factory create-content `
  --channel engineering-es `
  --topic "¿Por qué las tapas de alcantarilla son redondas?" `
  --research-provider local --script-generator local --scene-planner local `
  --narration-provider local --visual-provider local-placeholder `
  --caption-alignment local --renderer ffmpeg

python -m youtube_factory caption-project `
  --project-id <project-id> --channel engineering-es `
  --caption-alignment openai --output-dir output

python -m youtube_factory render-project `
  --project-id <project-id> --channel engineering-es --renderer ffmpeg

python -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp
python -m ruff check .
python -m ruff format --check .
python -m mypy src
git diff --check
```

All commands accept `--output-dir <path>`. `caption-project` aligns saved narration without
regenerating creative assets. `render-project` restyles persisted `captions.json` and renders
existing paid WAV/images without repeating OpenAI calls. Projects without captions still render
as Phase 5. The Phase 5 offline run produced
`output/2be33118-f60f-5d27-afcb-c9217dad79f5/render/short.mp4`: 1080x1920, 30 fps, H.264,
AAC, yuv420p, 36.733333 seconds and 128,952 bytes. The local WAV lasts 36.72 seconds; its audio
is intentionally silent. `render.json` and `manifest.json` were verified, and `render-project`
successfully rerendered the same saved inputs.

## Next Milestone

Phase 6B: optional per-word caption highlighting/emphasis driven by existing word alignment,
without changing canonical text or timing architecture. Human review remains required before
publication.
