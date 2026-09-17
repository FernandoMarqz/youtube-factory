# YouTube Factory - Fresh-Session Handoff

## Purpose And Status

Build a local-first, inspectable pipeline for a Spanish engineering/technology YouTube Shorts
channel. Human approval is required before any future publication. Python 3.12, Pydantic v2,
pytest, ruff and mypy are the current baseline. The architecture is a modular monolith with
domain contracts, application use cases/services, provider ports, infrastructure adapters and a
CLI composition root. PostgreSQL, FastAPI, n8n, publishing and analytics are deferred.

Phase 7B consumes the existing user-curated `assets/music/catalog.yaml` for offline,
deterministic soundtrack selection. Phase 7 still owns narration loudness normalization, optional
music ducking and encoded audio validation. Phase 6B per-word ASS emphasis remains intact;
the real WAV, canonical caption text and `TimedScenePlan` remain authoritative. FFmpeg
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
ASS captions are burned in after scene concatenation without changing audio mapping. The renderer
first analyzes narration with `loudnorm`, then applies measured two-pass normalization. Music is
selected from the catalog by default for `engineering-es`; disabled and manual modes remain.
The chosen project-relative audio file is validated,
looped or allowed to end, gain-adjusted, faded and ducked from the narration sidechain. Mixing
uses `amix=normalize=0`; a limiter leaves 1 dB AAC headroom. The final stereo 48 kHz AAC is
measured again. Audible normalized output must land within 2 LU of target and true peak within
0.25 dB of the configured ceiling. Silent local WAV fixtures skip the unattainable LUFS target.
No scene motion, text animation, AI music or publishing is implemented.

## Configuration And Artifacts

`.env` contains only secrets and machine-local output root. Version-controlled
`config/channels/engineering-es.yaml` has typed immutable research, script, scene planning,
narration, visuals, render, audio, captions and publishing sections. CLI override wins over channel
settings; there
is no implicit fallback. The channel defaults to local research/script/planning/visuals, OpenAI
narration, and FFmpeg rendering. Use the local narration override for an offline run.

Each project is under `data/projects/<project-id>/` by default, unless `.env` or `--output-dir`
overrides the root. It contains `topic.json`,
`research.json`, `script.json`, `scenes.json`, `narration.json`, `narration.wav`,
`timed-scenes.json`, `visual-prompts.json`, `visual-assets.json`, `assets/scene-XX.png`,
`word-alignment.json`, `captions.json`, `captions/captions.ass`, `selected-music.json`,
the selected `assets/music/<category>/<track>.mp3` copy, `audio-mix.json`, `render.json`, `render/short.mp4`
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
actual line break as it groups. New cues persist half-open word-index ranges. Old Phase 6 cues
without indexes resolve sequentially only if exact canonical tokens and timing containment
match. `captions.emphasis` has validated `#RRGGBB` active/inactive colors, `mode: word|none` and
an enable switch. Dynamic ASS uses sequential, non-overlapping full-cue states: fixed text,
wrap and geometry, with only the active acoustic word colored. Silence gaps show no highlight.
Absolute word boundaries are rounded independently to centiseconds. Turning emphasis off retains
static chunks. ASS defaults to bold Arial 64, white inactive text, warm yellow active text, dark
outline, small shadow and
450px bottom margin. The fixed relative libass
path is resolved from the project working directory to avoid Windows filter escaping.
The Phase 6 offline CLI smoke test produced a captioned 1080x1920, 30 fps H.264/AAC/yuv420p
MP4 at 36.733333 seconds. Phase 6B validated a real saved legacy plan (112 words, 27 cues)
read-only and generated 115 dynamic ASS events. FFmpeg-backed automated tests pass without any
paid call. Phase 7 audio config targets -16 LUFS and -1.5 dBTP; an explicitly supplied music
file must reside within each project (for example `assets/music/background.mp3`) and have suitable
YouTube usage rights. Phase 7B catalog mode loads all ten existing tracks with safe YAML and
library-relative path validation. Channel-configured Spanish keyword profiles infer a category,
moods, topics and energy from Topic + Script. Eligible tracks score suitable topic 4, mood 3,
profile category 3, niche 2, energy 2 (adjacent 1), and genre 1. Attribution-required tracks are
excluded unless configured otherwise. A SHA-256 topic-ID hash chooses from the sorted pool within
two points of the best score; no randomness or OpenAI call is used. The selected track and exact
catalog license fields are saved in `selected-music.json`, with an audio copy in the project.
Normal `render-project` reuses the persisted selection even if the catalog changes;
`--reselect-music` explicitly chooses again. Missing persisted audio fails. The catalog is
user-owned and is never rewritten by runtime; its licensing claims are not independently checked.
`audio-mix.json` stores actual input/final measurements and applied settings;
the manifest stores only mixer identity and music-enabled status. `render-project` changes audio
offline and does not rewrite WAV, visuals or semantic caption JSON. Listen on several speakers
before publication; synthetic tests cannot judge music taste or perceived pumping.

A copied 42-second OpenAI-narrated project was rerendered offline with music disabled. Its source
measured -18.62 LUFS; final AAC measured -16.18 LUFS and -2.42 dBTP at stereo 48 kHz. Source WAV
SHA-256 remained identical. The synthetic music/caption fixture verifies looping, ducking and
final media contracts; no new OpenAI call was made.

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
  --project-id <project-id> --channel engineering-es --renderer ffmpeg --output-dir output

python -m youtube_factory render-project `
  --project-id <project-id> --channel engineering-es --renderer ffmpeg `
  --reselect-music --output-dir output

python -m pytest -q -p no:cacheprovider --basetemp .pytest_tmp
python -m ruff check .
python -m ruff format --check .
python -m mypy src
git diff --check
```

All commands accept `--output-dir <path>`. `caption-project` aligns saved narration without
regenerating creative assets. `render-project` rebuilds ASS from persisted `captions.json` and
`word-alignment.json`, then renders saved WAV/images with zero OpenAI calls. It never rewrites
those semantic JSON files. Projects without captions still render as Phase 5. The Phase 5 offline
run produced
`output/2be33118-f60f-5d27-afcb-c9217dad79f5/render/short.mp4`: 1080x1920, 30 fps, H.264,
AAC, yuv420p, 36.733333 seconds and 128,952 bytes. The local WAV lasts 36.72 seconds; its audio
is intentionally silent. `render.json` and `manifest.json` were verified, and `render-project`
successfully rerendered the same saved inputs.

## Next Milestone

Phase 8: subtle deterministic Ken Burns scene motion and hard-cut polish without changing
authoritative scene timing. Human review remains required before publication.
