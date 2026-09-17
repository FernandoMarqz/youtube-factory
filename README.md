# youtube-factory

AI-assisted platform for generating, rendering, reviewing, publishing, and analyzing YouTube Shorts.

## Current stage

Phase 7B.1: deterministic content-profile inference for curated local music selection, followed by Phase 7 loudness and ducking. Rendering requires `ffmpeg` and
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
available, including caption burn-in; databases and publishing are not implemented yet.

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
1080x1920 and crops the overflow symmetrically. Hard cuts join scenes; the persisted
WAV becomes the AAC audio track. The target is 30 fps H.264/yuv420p in MP4. Phase 8 adds
optional still-image camera motion, but no generated video or transition effects. The final file is `render/short.mp4` and its
ffprobe-measured metadata is in `render.json`. `manifest.json` lists both and identifies the
renderer. Duration may differ from the WAV by at most two video frames (frame and AAC rounding).

## Phase 6/6B: narration-aligned captions and word emphasis

`captions.enabled` in channel YAML enables burned-in caption chunks. The local alignment
provider is deterministic and **synthetic**; it is for offline assembly only. For real speech,
select `--caption-alignment openai`. The configured `whisper-1` model supplies acoustic word
timestamps via `audio.transcriptions.create(response_format="verbose_json",
timestamp_granularities=["word"])`. OpenAI transcription never supplies display text: the
persisted `narration.narration_text` remains canonical. A normalized ordered comparison accepts
punctuation, case and accent differences, and rejects alignment below 90% matched canonical
tokens. Missing isolated tokens need a timing gap for interpolation or alignment fails.
An isolated zero-length OpenAI word interval may be repaired using at most 20 ms of adjacent
acoustic time; wholly degenerate or non-monotonic timestamp sequences still fail.

`word-alignment.json`, `captions.json` and `captions/captions.ass` remain inspectable. A deterministic
planner groups up to five words into cues, respects punctuation and duration limits, and wraps to
at most two lines. It checks the actual line break while grouping, not just total characters.
ASS burns bold text with a dark outline, small shadow and bottom-center
alignment 450 pixels above the bottom of a 1080x1920 frame. The fixed project-relative ASS filter
path is resolved from the project directory, avoiding Windows drive-letter escaping. Changing
channel caption style and running `render-project` regenerates ASS from `captions.json` and
`word-alignment.json` without another alignment or upstream AI call. Projects without a caption
plan still render uncaptioned.

Phase 6B adds optional per-word color emphasis. New cue plans persist contiguous
`word_start_index`/`word_end_index` ranges. Older plans without indexes are matched sequentially
against exact canonical tokens and rejected if they disagree. The channel's
`captions.emphasis` section controls `enabled`, `mode: word|none`, and `#RRGGBB` active/inactive
colors (default yellow `#FFD54A` over white `#FFFFFF`). Setting `enabled: false` or `mode: none`
retains static Phase 6 captions. Full-caption, non-overlapping ASS events keep one fixed wrap,
font and position while only the active word changes color. Speech gaps show all words in the
inactive color. Each event boundary is rounded independently to ASS centiseconds from the
persisted word timestamps; no durations are accumulated. The video frame rate limits visible
timing precision. Style changes require only `render-project`; neither semantic JSON is rewritten.

Offline full pipeline (the local WAV is deliberately silent):

```powershell
python -m youtube_factory create-content `
  --channel engineering-es `
  --topic "¿Por qué las tapas de alcantarilla son redondas?" `
  --research-provider local --script-generator local --scene-planner local `
  --narration-provider local --visual-provider local-placeholder `
  --caption-alignment local --renderer ffmpeg
```

To caption an existing project containing real speech and images without regenerating them, only
the alignment command makes one paid transcription call:

```powershell
python -m youtube_factory caption-project `
  --project-id <project-id> --channel engineering-es `
  --caption-alignment openai --output-dir output
python -m youtube_factory render-project `
  --project-id <project-id> --channel engineering-es `
  --renderer ffmpeg --output-dir output
```

The full paid pipeline can use all five OpenAI creative providers plus
`--caption-alignment openai`; it is never run automatically. FFmpeg must include libass, and the
selected font family must be resolvable on the host. On Windows, Arial is normally installed;
no font file is bundled.

## Phase 7: deterministic audio polish

The channel `audio` section normalizes the persisted narration toward -16 LUFS with a -1.5 dBTP
ceiling. FFmpeg performs a first-pass `loudnorm` measurement and applies the measured values in
the render pass. The final AAC is measured again; non-silent normalized narration must land within
2 LU of target, and measured true peak must stay within 0.25 dB of the configured ceiling. The
local fixture WAV is silent, so normalization and the LUFS target are skipped for that source;
silence is recorded explicitly in `audio-mix.json`. Output audio is centered stereo at 48 kHz.

The `engineering-es` channel now enables `catalog` mode. It reads the existing, user-curated
`assets/music/catalog.yaml` without modifying the catalog or acquiring new music. Selection
is deterministic: channel keyword profiles match Spanish topic/script text, then catalog topic,
mood, category, niche, energy and genre metadata contribute to a weighted score. Tracks requiring
attribution are excluded by this channel. A stable topic hash chooses among tracks within two
points of the best score. The chosen track and the catalog's license metadata are saved in
`selected-music.json`; the audio is copied into the project so later renders are reproducible.
Phase 7B.1 builds a separate `ContentMusicProfile` from topic title plus structured script text.
Matching ignores case, accents and punctuation while respecting word boundaries, including
multi-word phrases. Phrase matches count 3; token matches count 1. The strongest specific profile
wins (name breaks ties), while relevant secondary and educational profiles add signals. The
primary profile sets energy; channel defaults apply when nothing matches. `selected-music.json`
records the primary profile, matching profiles/keywords and inferred topics/moods separately
from matches with the chosen catalog track. Catalog scoring weights and audio mixing are unchanged.

The three modes are `disabled` (`enabled: false`), `manual` (`enabled: true`, `mode: manual`,
project-relative `file_path`) and `catalog` (`enabled: true`, `mode: catalog`, no `file_path`).
Manual mode retains the Phase 7 behavior. For example:

```yaml
audio:
  narration:
    normalize: true
    target_lufs: -16.0
    true_peak_db: -1.5
  music:
    enabled: true
    mode: manual
    file_path: assets/music/background.mp3
    gain_db: -22.0
    loop: true
    fade_in_seconds: 0.6
    fade_out_seconds: 1.2
  ducking:
    enabled: true
    threshold: 0.03
    ratio: 8.0
    attack_ms: 80
    release_ms: 350
```

For catalog mode, use `mode: catalog`, `file_path: null`, and
`catalog_path: assets/music/catalog.yaml` with channel `selection` preferences. The catalog
path is repository-relative; each track path is resolved relative to the catalog. The chosen
file must contain a readable audio stream. Music is resampled to stereo,
trimmed to narration length, optionally looped, faded and lowered by its baseline gain. The
normalized narration controls `sidechaincompress`, so music recovers during pauses. A conservative
limiter follows mixing; `amix` does not apply its implicit input normalization. Music shorter than
the Short ends naturally when `loop: false`, with fade-out at that track's end. No music is
downloaded or generated. Catalog license fields are recorded as supplied, not independently
verified; check actual usage rights before publishing.

Change channel audio settings and rerender persisted media without TTS, images, captions or other
OpenAI calls:

```powershell
python -m youtube_factory render-project `
  --project-id <project-id> --channel engineering-es `
  --renderer ffmpeg --output-dir output
```

`audio-mix.json` records measured input/final loudness, true peak and applied settings;
`manifest.json` records the audio mixer and selector identities. Source WAV, captions and visual
artifacts remain unchanged. In catalog mode, `render-project` reuses `selected-music.json` even if the catalog
changes; `--reselect-music` explicitly chooses again. If its project-local MP3 is missing, render
fails rather than changing the soundtrack. To add tracks later, download manually, put the file
under `assets/music/`, add an entry with exact license metadata, and validate the catalog by
running `python -m pytest -q tests/test_music.py`. Listen on headphones, laptop and phone speakers for clarity, pumping, clipping,
pauses and the first/last second; measurements do not replace listening review.

To deliberately change the selected track for an existing project:

```powershell
python -m youtube_factory render-project `
  --project-id <project-id> --channel engineering-es `
  --renderer ffmpeg --reselect-music --output-dir output
```

```powershell
python -m youtube_factory create-content `
  --channel engineering-es `
  --topic "¿Por qué los puentes tienen juntas de dilatación?" `
  --research-provider openai --script-generator openai --scene-planner openai `
  --narration-provider openai --visual-provider openai `
  --caption-alignment openai --renderer ffmpeg
```

This full paid command is documentation only; Phase 7B itself makes no AI call. Review
several cues, a two-line cue, punctuation, a fast phrase, a pause, and first/last captions before
any eventual publication.

## Phase 8: deterministic scene motion

The channel `visual_motion` section adds restrained motion to the existing PNGs. A provider-neutral
planner derives `visual-motion.json` from `TimedScenePlan`, the visual manifest and channel settings;
it uses a stable topic/scene hash for variety and avoids repeated adjacent motions. Supported moves
are static, slow zoom in/out, pan left/right/up/down and pan with zoom. Zoom is limited to 1.07 by
default; the configured pan limit is 4% of the prepared image. FFmpeg's `zoompan` uses a 125% cover
canvas and bounded crop coordinates, so it cannot reveal empty edges. Each scene emits exactly its
rounded authoritative frame count. Cuts remain hard; free-text transition suggestions are retained
as metadata, not executed. Captions are burned after scene concatenation and the Phase 7 audio graph
is unchanged.

`render-project` rebuilds the motion plan and MP4 from saved media with zero provider calls. It
updates only render-derived artifacts; narration, captions, selected music and visual assets remain
untouched. Set `visual_motion.enabled: false` to retain static Phase 7 behavior. Review the full
video for smoothness and composition before publication.

## Phase 8B: intra-scene visual pacing

`visual_pacing` optionally divides a long scene into **at most two** frame-exact beats from its
existing PNG and Phase 8 `SceneMotion`. Animation-intent scenes qualify from 6.5 seconds, ordinary
images from 8 seconds; diagrams stay at one beat. Both beats must last at least 2.5 seconds. A
stable topic/scene hash chooses a 45/50/55% first-beat ratio, rounded against the scene's absolute
frame boundaries. The second beat starts at the first beat's terminal crop/zoom, then changes
direction gently. This is camera pacing, not object animation or a second generated image.

`visual-motion.json` remains the scene style; `visual-pacing.json` records the derived beats and
their absolute frame ranges. FFmpeg splits a prepared image into two `zoompan` branches only for
two-beat scenes, concatenates those branches, then follows its existing scene concat, ASS and
audio paths. Set `visual_pacing.enabled: false` for the Phase 8 one-beat behavior. Running
`render-project` rebuilds both plans offline, without changing the WAV, semantic captions,
selected music or source PNGs. Scene-to-scene and intra-scene transitions remain hard cuts.

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
  --caption-alignment openai `
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

## Phase 9: selective generated video

Phase 8/8B remains the default. Optional Phase 9 plans at most one five-second image-to-video
clip for a long `animation` scene with two visual beats. Planning is deterministic and free;
generation is disabled by default. The existing PNG is center-cover fitted to a derived
720x1280 JPEG reference without stretching or source mutation. A validated generated clip
replaces only beat 2. FFmpeg trims it to exact frames, rescales to 1080x1920, ignores provider
audio, and applies unchanged captions and audio downstream. Invalid or absent clips fall back
to Phase 8B during offline `render-project`.

Install the optional official SDK with `pip install -e ".[runway]"`; put
`RUNWAYML_API_SECRET` in ignored `.env`. Before a paid call, set
`generative_video.enabled: true` in channel YAML. Ordinary `create-content` also requires an
explicit `--video-provider runway` flag to spend video credits. No test uses Runway.

```powershell
# Free planning; works while generation is disabled
python -m youtube_factory generate-video-assets `
  --project-id eb72074f-ab9f-5dcb-9de2-fcafd3029f85 `
  --channel engineering-es --provider runway --dry-run --output-dir output

# Paid, only after explicit channel opt-in
python -m youtube_factory generate-video-assets `
  --project-id eb72074f-ab9f-5dcb-9de2-fcafd3029f85 `
  --channel engineering-es --provider runway --output-dir output

# Offline reuse/fallback
python -m youtube_factory render-project `
  --project-id eb72074f-ab9f-5dcb-9de2-fcafd3029f85 `
  --channel engineering-es --renderer ffmpeg --output-dir output
```

`generative-video-plan.json` records eligibility, score, prompt and requested seconds.
Success adds `video-references/scene-XX.jpg`, `generated-video/scene-XX.mp4`, and
`generated-video-assets.json` with measured media properties, task ID, timestamps, and
source/prompt hashes. Existing clips are reused; `--regenerate` explicitly replaces one.
No cost is invented if Runway does not report it. Human review remains mandatory.

Run the quality checks:

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy
```
