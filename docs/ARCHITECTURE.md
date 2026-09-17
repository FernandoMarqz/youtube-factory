# Architecture

## Current System

Python 3.12 modular monolith. Pydantic v2 contracts live in `domain`, orchestration in
`application`, capability interfaces in `ports`, external implementations in `adapters`, and
composition in `cli`. Domain models contain no provider SDK types. There is no database, API,
publisher or n8n workflow yet.

```text
Topic -> ResearchResult -> Script -> ScenePlan -> Narration + narration.wav
      -> TimedScenePlan -> VisualPromptPlan -> VisualAssetManifest
      -> CaptionAlignmentProvider -> WordAlignment -> CaptionPlanner -> CaptionPlan
      -> ASS -> Renderer -> RenderArtifact
```

The render input also carries typed audio intent: persisted narration WAV plus optional
project-local music. In catalog mode, an application selector chooses from the existing curated
`assets/music/catalog.yaml`, persists `selected-music.json` and copies audio into the project.
Audio analysis/mixing remains in the FFmpeg adapter; it never sees catalog scoring metadata.
`ContentMusicProfileBuilder` separately infers typed intent from Topic + Script with
channel-configured Spanish phrases/tokens. `MusicCatalogScorer` consumes that profile while
retaining Phase 7B weights; the selector applies eligibility and stable-hash variety.

`CreateContentUseCase` orchestrates the creative stages and persists their artifacts through
`ProjectArtifactStore`. The CLI then invokes `RenderProjectUseCase`, which loads those persisted
media artifacts through the same store and calls a provider-neutral `Renderer`. `render-project`
invokes only the latter use case, so existing paid inputs are reusable without regeneration.
`CaptionProjectUseCase` separately loads persisted WAV and canonical narration text, aligns and
persists captions without any creative-stage call. The CLI runs it before rendering when captions
are enabled. `render-project` can restyle persisted semantic cues without realignment and reuse
an already-selected soundtrack without loading the catalog.

## Provider Boundaries

| Port | Current adapters |
| --- | --- |
| `ResearchProvider` | Local fixture, OpenAI web-search research |
| `ScriptGenerator` | Local fixture, OpenAI grounded script generation |
| `ScenePlanner` | Local fixture, OpenAI semantic scene planning |
| `NarrationGenerator` | Local silent WAV fixture, OpenAI TTS |
| `VisualAssetProvider` | Local placeholder PNG, OpenAI image generation |
| `ProjectArtifactStore` | Local filesystem |
| `Renderer` | `FFmpegRenderer` |
| `CaptionAlignmentProvider` | Local synthetic alignment, OpenAI word-timestamp transcription |

The OpenAI adapters validate provider-private structured results before mapping them to domain
contracts. Research persists URLs backed by web-search evidence. Script generation consumes only
validated research, references exact persisted facts, and builds its narration/duration in Python.
If the deterministic estimate falls outside the channel's Short bounds, the OpenAI script adapter
makes one grounded rewrite request and recalculates. It persists only the accepted script.
The semantic AI scene plan reconstructs the full narration and normalizes provisional pacing to
the script's estimated duration.

Caption text comes only from `Narration.narration_text`; transcription is timing evidence. The
OpenAI adapter uses `whisper-1` verbose JSON word timestamps, then normalized character sequence
alignment to reconcile punctuation, case, quotes and accents. At least 90% of canonical tokens
must match. Local alignment is marked synthetic. A deterministic planner groups aligned words;
ASS generation is derived from the semantic caption plan, persisted word alignment and channel
style. Phase 6B stores contiguous word-index ranges on new cues; old cues resolve against the
canonical word sequence with exact token and timestamp-containment checks. The alignment and
cue grouping algorithms are unchanged.

## Timing And Media

`scenes.json` is the provisional semantic plan. OpenAI/local narration is normalized to mono
16-bit PCM WAV and measured. `SceneTimingReconciler` scales provisional scene durations to that
real audio length; `timed-scenes.json` starts at zero, is continuous, and ends at the measured WAV
duration. The renderer uses only this authoritative timed plan.

`VisualPromptPlan` is built from timed scenes and channel style, separately from semantic scene
descriptions. `VisualAssetManifest` maps one persisted PNG to each scene with dimensions and a
prompt hash. `ANIMATION` remains editorial intent; the current provider still yields a static PNG.

`FFmpegRenderer` resolves `ffmpeg` and `ffprobe` on PATH and passes argument arrays to subprocess
with a 600-second timeout. Its filter graph emits the frame interval obtained by rounding timed
start/end boundaries to the configured FPS. Static scenes retain the original cover/crop filter;
motion scenes use bounded `zoompan` on a proportionally scaled cover canvas. All scenes concatenate
with hard cuts.
When a caption plan exists and captions are enabled, FFmpeg appends a libass filter after scene
concatenation. The ASS path is fixed and project-relative, and FFmpeg runs with the project as its
working directory to avoid Windows drive-colon and space escaping. Caption burn-in leaves audio
mapping unchanged. The persisted WAV is encoded as AAC alongside H.264 video in an MP4. A
dynamic ASS file uses sequential, non-overlapping full-caption events rather than overlapping
text layers or karaoke tags. Every state shares the same two-line wrap and position; an inline
ASS primary-color override marks only the word active at the persisted acoustic time. Silence
gaps have no highlighted word. Event boundaries use independently rounded absolute centiseconds,
so there is no accumulated timing drift. `render-project` rebuilds ASS from both semantic JSON
artifacts without an alignment or creative provider call. Phase 7 extends the same renderer's
audio path: it measures the source WAV with `loudnorm`, applies second-pass normalization, and
optionally loads one validated project-local music file. Music is resampled to stereo,
gain-adjusted, looped or ended naturally, trimmed, faded and ducked by the narration sidechain.
`amix=normalize=0` preserves narration level; a limiter with 1 dB encoding headroom protects the
mix. The AAC output is stereo 48 kHz. A second measurement of the encoded MP4 validates
integrated LUFS (within 2 LU when audible normalization is enabled) and true peak (ceiling plus
at most 0.25 dB). Silent local WAV fixtures skip the unattainable LUFS target. Source media is
never rewritten.
A temporary `.short-part.mp4`
under the project's `render/` directory is replaced with `short.mp4` only after ffprobe validates
the file. No scene clips or OS-global temporary files are needed.

Probe validation checks a nonempty file, video and audio streams, actual codecs, dimensions,
pixel format, frame rate, and duration within two frames of the narration-derived timeline. The
tolerance covers frame and AAC/container rounding. `render.json` contains measured values.

## Configuration And Artifacts

`.env` holds secrets and machine-local output location. `config/channels/engineering-es.yaml`
holds immutable typed editorial, provider and render settings. Explicit CLI provider flags override
the selected channel for one invocation. No provider fallback occurs.

```text
data/projects/<project-id>/
  topic.json
  research.json
  script.json
  scenes.json
  narration.json
  narration.wav
  timed-scenes.json
  visual-prompts.json
  visual-assets.json
  assets/scene-XX.png
  word-alignment.json
  captions.json
  captions/captions.ass
  selected-music.json
  assets/music/<category>/<track>.mp3
  audio-mix.json
  visual-motion.json
  visual-pacing.json
  render.json
  render/short.mp4
  manifest.json
```

The artifact store validates persisted WAV, scene count/sequence and PNG content before passing
render inputs to the renderer. It writes `render.json` and extends `manifest.json` only after a
successful render. Source JSON and PNG/WAV artifacts remain inspectable for retry and review.
`audio-mix.json` contains actual measurements and mix settings; manifest metadata identifies the
audio mixer without duplicating the report. `selected-music.json` records the chosen track,
score, matched signals and verbatim curated license metadata; manifest metadata stores only the
selector identity and track ID. The catalog loader validates all paths structurally, while the
existing FFmpeg media probe validates the selected file's audio stream. Caption chunks and static per-word color emphasis
remain intact. Phase 8 derives `VisualMotionPlan` from timed scenes, assets and typed channel
settings on every render. The FFmpeg adapter converts this provider-neutral plan to a bounded
`zoompan` filter per scene, with exact rounded scene frame counts and hard cuts. Its 125% cover
canvas preserves aspect ratio and provides resampling headroom; crop positions remain within the
image. Captions and audio are applied after visual composition. The artifact store persists
`visual-motion.json` and a small manifest identity, without changing source assets. Publishing
and analytics are later work.

Phase 8B derives `VisualPacingPlan` from the same timed scenes and assets plus the saved
`VisualMotionPlan`. Each `SceneVisualPacing` has one or two `VisualBeat` entries whose absolute
frame ranges partition exactly the rounded scene boundaries. A second beat is favored for long
animation-intent scenes and long images; diagrams stay single-beat. The second camera trajectory
starts at the first's terminal geometry. The FFmpeg adapter reuses its image preparation and
`zoompan` expressions, splitting one PNG input into two filter branches only when necessary.
Beat concat happens before the unchanged global scene concat; captions and audio stay downstream.
`visual-pacing.json` and minimal manifest metadata are render-derived, not new editorial timing.

Phase 9 is optional: `GenerativeVideoEligibilityPolicy` consumes the saved semantic scene plan,
timed scene plan, visual asset manifest and Phase 8B pacing, producing a free
`GenerativeVideoPlan`. The provider-neutral `VideoAssetProvider` has a local fixture adapter
and an optional paid Runway adapter. An explicit generation use case creates a derived 9:16
reference image, submits at most one task, validates the downloaded MP4 through a media
inspector port and persists a `GeneratedVideoManifest`. `render-project` never calls this port.
It derives a hybrid visual composition only from persisted valid clips; otherwise Phase 8B
renders as before. FFmpeg normalizes and trims a clip to beat 2's exact frame count, maps no
provider audio, then uses the existing scene concat, ASS and audio graph. No semantic scene,
caption, narration or music timeline changes.
