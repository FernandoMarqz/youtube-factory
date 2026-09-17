"""Offline render boundary tests and optional real FFmpeg coverage."""

import json
import shutil
import subprocess
import wave
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageStat
from pydantic import ValidationError

from youtube_factory.adapters.ffmpeg import FFmpegRenderer
from youtube_factory.adapters.local import FileSystemArtifactStore
from youtube_factory.application.config import (
    RenderConfig,
    VisualMotionConfig,
    VisualPacingConfig,
    load_channel_config,
)
from youtube_factory.application.exceptions import (
    RenderError,
    RendererUnavailableError,
    RenderValidationError,
)
from youtube_factory.application.services.visual_motion import DeterministicVisualMotionPlanner
from youtube_factory.application.services.visual_pacing import DeterministicVisualPacingPlanner
from youtube_factory.application.use_cases import RenderProjectUseCase
from youtube_factory.domain.enums import AssetType
from youtube_factory.domain.models import (
    ContentManifest,
    Narration,
    RenderArtifact,
    ResearchProviderMetadata,
    Scene,
    ScriptGeneratorMetadata,
    TimedScenePlan,
    VisualAsset,
    VisualAssetManifest,
    VisualBeat,
    VisualPacingPlan,
)
from youtube_factory.ports import RenderInputs


def fixture_project(tmp_path: Path) -> tuple[str, FileSystemArtifactStore, RenderInputs]:
    """Persist two one-second scenes with a silent PCM WAV and distinct PNGs."""
    topic_id = uuid4()
    project_id = str(topic_id)
    directory = tmp_path / project_id
    (directory / "assets").mkdir(parents=True)
    audio = BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 32000)
    (directory / "narration.wav").write_bytes(audio.getvalue())
    narration = Narration(
        topic_id=topic_id,
        file_path="narration.wav",
        duration_seconds=2,
        provider="local",
        voice="fixture",
        sample_rate_hz=16000,
        narration_text="Test narration",
        script_sha256="a" * 64,
    )
    scenes = [
        Scene(
            sequence=sequence,
            narration_segment=f"segment {sequence}",
            start_seconds=float(sequence - 1),
            end_seconds=float(sequence),
            duration_seconds=1,
            visual_description="Visual",
            visual_intent="Explain",
            asset_type=AssetType.IMAGE,
        )
        for sequence in (1, 2)
    ]
    timed = TimedScenePlan(
        topic_id=topic_id,
        source_total_duration_seconds=2,
        narration_duration_seconds=2,
        total_duration_seconds=2,
        reconciliation_strategy="fixture",
        scenes=scenes,
    )
    assets = []
    for sequence, color in ((1, (200, 30, 30)), (2, (30, 200, 30))):
        path = f"assets/scene-{sequence:02d}.png"
        Image.new("RGB", (64, 96), color).save(directory / path)
        assets.append(
            VisualAsset(
                scene_sequence=sequence,
                provider="local-placeholder",
                file_path=path,
                width=64,
                height=96,
                prompt_sha256="b" * 64,
            )
        )
    visuals = VisualAssetManifest(
        topic_id=topic_id,
        channel_id="engineering-es",
        provider="local-placeholder",
        assets=assets,
    )
    manifest = ContentManifest(
        project_id=topic_id,
        pipeline_version="fixture",
        channel_id="engineering-es",
        topic="Fixture",
        topic_id=topic_id,
        artifacts=(
            "narration.json",
            "narration.wav",
            "timed-scenes.json",
            "visual-assets.json",
            "manifest.json",
        ),
        research_provider=ResearchProviderMetadata(provider="local", identifier="fixture"),
        script_generator=ScriptGeneratorMetadata(provider="local", identifier="fixture"),
    )
    for name, model in (
        ("narration.json", narration),
        ("timed-scenes.json", timed),
        ("visual-assets.json", visuals),
        ("manifest.json", manifest),
    ):
        (directory / name).write_text(model.model_dump_json(), encoding="utf-8")
    store = FileSystemArtifactStore(tmp_path)
    return project_id, store, RenderInputs(directory, narration, timed, visuals)


def test_render_config_is_strict_immutable_and_validated() -> None:
    config = load_channel_config("engineering-es").render
    assert (config.width, config.height, config.fps) == (1080, 1920, 30)
    with pytest.raises(ValidationError):
        config.fps = 25
    for change in (
        {"width": 0},
        {"height": 0},
        {"fps": 0},
        {"provider": "unknown"},
        {"width": 1081},
        {"height": 1000},
        {"video_codec": ""},
        {"audio_codec": ""},
        {"pixel_format": ""},
    ):
        with pytest.raises(ValidationError):
            RenderConfig.model_validate(config.model_dump() | change)


def test_render_artifact_rejects_non_project_paths() -> None:
    artifact = RenderArtifact(
        provider="ffmpeg",
        file_path="render/short.mp4",
        duration_seconds=2,
        width=1080,
        height=1920,
        frame_rate=30,
        video_codec="h264",
        audio_codec="aac",
        pixel_format="yuv420p",
        file_size_bytes=100,
    )
    for path in ("../short.mp4", "C:\\video\\short.mp4", "render\\short.mp4"):
        with pytest.raises(ValidationError):
            RenderArtifact.model_validate(artifact.model_dump() | {"file_path": path})


def test_visual_motion_config_and_deterministic_plan(tmp_path: Path) -> None:
    _, _, inputs = fixture_project(tmp_path)
    config = load_channel_config("engineering-es").visual_motion
    planner = DeterministicVisualMotionPlanner()
    first = planner.plan(inputs.timed_scene_plan, inputs.visual_assets, config, 30)
    assert first == planner.plan(inputs.timed_scene_plan, inputs.visual_assets, config, 30)
    assert first.enabled and len(first.scenes) == 2
    assert all(config.zoom_min <= motion.start_zoom <= config.zoom_max for motion in first.scenes)
    assert all(config.zoom_min <= motion.end_zoom <= config.zoom_max for motion in first.scenes)
    assert first.scenes[0].motion_type != first.scenes[1].motion_type
    disabled = planner.plan(inputs.timed_scene_plan, inputs.visual_assets, VisualMotionConfig(), 30)
    assert {scene.motion_type for scene in disabled.scenes} == {"static"}
    with pytest.raises(ValidationError):
        config.enabled = False
    for change in (
        {"zoom_min": 0.9},
        {"zoom_max": 2.0},
        {"zoom_min": 1.1, "zoom_max": 1.05},
        {"pan_max_percent": -0.1},
        {"allowed_motion_types": ["spin"]},
        {"allowed_motion_types": []},
        {"transition_type": "crossfade"},
    ):
        with pytest.raises(ValidationError):
            VisualMotionConfig.model_validate(config.model_dump() | change)


def test_motion_uses_asset_type_and_simple_visual_hint(tmp_path: Path) -> None:
    _, _, inputs = fixture_project(tmp_path)
    scenes = inputs.timed_scene_plan.scenes
    timed = inputs.timed_scene_plan.model_copy(
        update={
            "scenes": [
                scenes[0].model_copy(update={"visual_description": "Primer plano de piedra"}),
                scenes[1].model_copy(update={"asset_type": AssetType.ANIMATION}),
            ]
        }
    )
    config = VisualMotionConfig(enabled=True, allowed_motion_types=("slow_zoom_in", "pan_zoom_out"))
    plan = DeterministicVisualMotionPlanner().plan(timed, inputs.visual_assets, config, 30)
    assert [motion.motion_type for motion in plan.scenes] == ["slow_zoom_in", "pan_zoom_out"]


def _pacing_plan(
    tmp_path: Path,
    duration: float,
    asset_type: AssetType,
    pacing: VisualPacingConfig | None = None,
) -> VisualPacingPlan:
    _, _, inputs = fixture_project(tmp_path)
    scene = Scene.model_validate(
        inputs.timed_scene_plan.scenes[0].model_dump()
        | {
            "start_seconds": 0,
            "end_seconds": duration,
            "duration_seconds": duration,
            "asset_type": asset_type,
        }
    )
    timed = TimedScenePlan.model_validate(
        inputs.timed_scene_plan.model_dump()
        | {
            "scenes": [scene],
            "total_duration_seconds": duration,
            "narration_duration_seconds": duration,
        }
    )
    assets = inputs.visual_assets.model_copy(update={"assets": inputs.visual_assets.assets[:1]})
    channel = load_channel_config("engineering-es")
    motion = DeterministicVisualMotionPlanner().plan(timed, assets, channel.visual_motion, 30)
    planner = DeterministicVisualPacingPlanner()
    settings = pacing or channel.visual_pacing
    plan = planner.plan(timed, motion, assets, settings, channel.visual_motion)
    assert plan == planner.plan(timed, motion, assets, settings, channel.visual_motion)
    return plan


@pytest.mark.parametrize(
    ("duration", "asset_type", "expected"),
    [
        (2.365, AssetType.DIAGRAM, 1),
        (4.5, AssetType.IMAGE, 1),
        (6.8, AssetType.ANIMATION, 2),
        (8.815, AssetType.ANIMATION, 2),
        (9.0, AssetType.IMAGE, 2),
        (9.0, AssetType.DIAGRAM, 1),
    ],
)
def test_duration_and_asset_aware_visual_beats(
    tmp_path: Path, duration: float, asset_type: AssetType, expected: int
) -> None:
    plan = _pacing_plan(tmp_path, duration, asset_type)
    scene = plan.scenes[0]
    assert len(scene.beats) == expected
    assert sum(beat.frame_count for beat in scene.beats) == round(duration * 30)
    assert scene.beats[-1].end_frame == round(duration * 30)
    if expected == 2:
        first, second = scene.beats
        assert min(first.frame_count, second.frame_count) >= 75
        assert first.end_frame == second.start_frame
        assert first.end_zoom == second.start_zoom
        assert first.pan_x_end == second.pan_x_start
        assert first.pan_y_end == second.pan_y_start
        assert first.motion_type != second.motion_type


def test_visual_pacing_config_contracts_and_disabled_mode(tmp_path: Path) -> None:
    config = load_channel_config("engineering-es").visual_pacing
    with pytest.raises(ValidationError):
        config.enabled = False
    for change in (
        {"max_beats_per_scene": 0},
        {"max_beats_per_scene": 3},
        {"min_beat_duration_seconds": 0},
        {"second_beat_seconds": 9},
        {"split_ratios": [0.2]},
        {"split_ratios": []},
    ):
        with pytest.raises(ValidationError):
            VisualPacingConfig.model_validate(config.model_dump() | change)
    plan = _pacing_plan(tmp_path, 9.0, AssetType.IMAGE)
    assert len(plan.scenes[0].beats) == 2
    disabled = _pacing_plan(
        tmp_path, 9.0, AssetType.IMAGE, config.model_copy(update={"enabled": False})
    )
    assert len(disabled.scenes[0].beats) == 1
    with pytest.raises(ValidationError):
        VisualBeat.model_validate(plan.scenes[0].beats[0].model_dump() | {"frame_count": 1})
    with pytest.raises(ValidationError):
        VisualPacingPlan.model_validate(
            plan.model_dump() | {"scenes": [{**plan.scenes[0].model_dump(), "end_frame": 1}]}
        )


def test_store_rejects_missing_media_and_asset_count(tmp_path: Path) -> None:
    project_id, store, inputs = fixture_project(tmp_path)
    assert store.load_render_inputs(project_id) == inputs
    (inputs.project_directory / "narration.wav").unlink()
    with pytest.raises(RenderValidationError, match="missing or invalid"):
        store.load_render_inputs(project_id)
    (inputs.project_directory / "narration.wav").write_bytes(b"bad")
    with pytest.raises(RenderValidationError, match="missing or invalid"):
        store.load_render_inputs(project_id)
    project_id, store, inputs = fixture_project(tmp_path)
    (inputs.project_directory / inputs.visual_assets.assets[0].file_path).unlink()
    with pytest.raises(RenderValidationError, match="missing or invalid"):
        store.load_render_inputs(project_id)
    (inputs.project_directory / "visual-assets.json").write_text(
        inputs.visual_assets.model_copy(
            update={"assets": inputs.visual_assets.assets[:1]}
        ).model_dump_json(),
        encoding="utf-8",
    )
    with pytest.raises(RenderValidationError, match="counts differ"):
        store.load_render_inputs(project_id)


def test_store_rejects_invalid_png_and_unsafe_project_id(tmp_path: Path) -> None:
    project_id, store, inputs = fixture_project(tmp_path)
    (inputs.project_directory / inputs.visual_assets.assets[0].file_path).write_bytes(b"bad png")
    with pytest.raises(RenderValidationError, match="not a valid PNG"):
        store.load_render_inputs(project_id)
    with pytest.raises(RenderValidationError, match="project id must be a UUID"):
        store.load_render_inputs("../escape")


def test_duplicate_asset_sequence_is_rejected(tmp_path: Path) -> None:
    project_id, store, inputs = fixture_project(tmp_path)
    payload = inputs.visual_assets.model_dump(mode="json")
    payload["assets"][1]["scene_sequence"] = 1
    (inputs.project_directory / "visual-assets.json").write_text(json.dumps(payload), "utf-8")
    with pytest.raises(RenderValidationError, match="missing or invalid"):
        store.load_render_inputs(project_id)


def test_render_use_case_passes_persisted_inputs_and_saves_metadata(tmp_path: Path) -> None:
    project_id, store, inputs = fixture_project(tmp_path)

    class RecordingRenderer:
        provider = "ffmpeg"
        identifier = "test-renderer"
        received: RenderInputs | None = None

        def render(self, value: RenderInputs, config: RenderConfig) -> RenderArtifact:
            self.received = value
            assert config.fps == 30
            (value.project_directory / "render").mkdir()
            (value.project_directory / "render/short.mp4").write_bytes(b"fixture")
            return RenderArtifact(
                provider="ffmpeg",
                file_path="render/short.mp4",
                duration_seconds=2,
                width=1080,
                height=1920,
                frame_rate=30,
                video_codec="h264",
                audio_codec="aac",
                pixel_format="yuv420p",
                file_size_bytes=7,
            )

    renderer = RecordingRenderer()
    artifact = RenderProjectUseCase(
        store, renderer, load_channel_config("engineering-es").render
    ).execute(project_id)
    assert renderer.received == inputs
    assert (
        RenderArtifact.model_validate_json(
            (inputs.project_directory / "render.json").read_text("utf-8")
        )
        == artifact
    )
    manifest = ContentManifest.model_validate_json(
        (inputs.project_directory / "manifest.json").read_text("utf-8")
    )
    assert "render.json" in manifest.artifacts
    assert "render/short.mp4" in manifest.artifacts
    assert manifest.renderer is not None and manifest.renderer.identifier == "test-renderer"


def test_executable_discovery_and_argument_array(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, _, inputs = fixture_project(tmp_path)
    config = load_channel_config("engineering-es").render
    command = FFmpegRenderer.build_command("ffmpeg", inputs, config, tmp_path / "out.mp4")
    assert command[0] == "ffmpeg"
    assert "-filter_complex" in command
    graph = command[command.index("-filter_complex") + 1]
    assert "trim=end_frame=30" in graph
    assert "force_original_aspect_ratio=increase" in graph
    assert "crop=1080:1920" in graph
    assert "concat=n=2:v=1:a=0" in graph
    assert "narration.wav" in " ".join(command)
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "ffmpeg" else name)
    with pytest.raises(RendererUnavailableError, match="ffmpeg executable not found"):
        FFmpegRenderer().check_available()
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "ffprobe" else name)
    with pytest.raises(RendererUnavailableError, match="ffprobe executable not found"):
        FFmpegRenderer().check_available()


def test_subprocess_failures_and_probe_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    renderer = FFmpegRenderer()
    calls: list[dict[str, object]] = []

    def fail(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(kwargs)
        return subprocess.CompletedProcess(command, 1, "", "decode failure")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(RenderError, match="decode failure"):
        renderer._run(["ffmpeg", "-i", "input.png"], "FFmpeg")
    assert calls[0]["check"] is False
    assert "shell" not in calls[0]
    _, _, inputs = fixture_project(tmp_path)
    output = tmp_path / "invalid.mp4"
    output.write_bytes(b"not a movie")
    monkeypatch.setattr(renderer, "_run", lambda command, stage: "{}")
    with pytest.raises(RenderValidationError, match="invalid video or audio metadata"):
        renderer._probe("ffprobe", output, inputs, load_channel_config("engineering-es").render)

    valid_probe = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1080,
                "height": 1920,
                "avg_frame_rate": "30/1",
                "pix_fmt": "yuv420p",
            },
            {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2},
        ],
        "format": {"duration": "5.0"},
    }
    monkeypatch.setattr(renderer, "_run", lambda command, stage: json.dumps(valid_probe))
    with pytest.raises(RenderValidationError, match="differs"):
        renderer._probe("ffprobe", output, inputs, load_channel_config("engineering-es").render)


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is unavailable"
)
def test_real_short_mp4_from_two_static_scenes(tmp_path: Path) -> None:
    project_id, store, _ = fixture_project(tmp_path)
    artifact = RenderProjectUseCase(
        store, FFmpegRenderer(), load_channel_config("engineering-es").render
    ).execute(project_id)
    assert artifact.file_size_bytes > 0
    assert (artifact.width, artifact.height, artifact.frame_rate) == (1080, 1920, 30)
    assert (artifact.video_codec, artifact.audio_codec, artifact.pixel_format) == (
        "h264",
        "aac",
        "yuv420p",
    )
    assert abs(artifact.duration_seconds - 2) <= 2 / 30


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is unavailable"
)
def test_motion_changes_real_frames_without_changing_duration(tmp_path: Path) -> None:
    project_id, store, inputs = fixture_project(tmp_path)
    for asset in inputs.visual_assets.assets:
        image = Image.new("RGB", (64, 96), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((5, 7, 42, 65), fill="black")
        draw.ellipse((27, 30, 58, 82), fill="red")
        image.save(inputs.project_directory / asset.file_path)
    channel = load_channel_config("engineering-es")
    artifact = RenderProjectUseCase(
        store, FFmpegRenderer(), channel.render, visual_motion=channel.visual_motion
    ).execute(project_id)
    assert abs(artifact.duration_seconds - 2) <= 2 / 30
    assert (artifact.width, artifact.height, artifact.frame_rate) == (1080, 1920, 30)
    plan = json.loads((inputs.project_directory / "visual-motion.json").read_text("utf-8"))
    assert any(scene["motion_type"] != "static" for scene in plan["scenes"])
    assert (
        "visual-motion.json"
        in json.loads((inputs.project_directory / "manifest.json").read_text("utf-8"))["artifacts"]
    )
    video = inputs.project_directory / "render/short.mp4"
    count = subprocess.run(
        [
            shutil.which("ffprobe") or "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert int(count.stdout.strip()) == 60
    frames = []
    for instant in ("0.05", "0.85"):
        result = subprocess.run(
            [
                shutil.which("ffmpeg") or "ffmpeg",
                "-v",
                "error",
                "-ss",
                instant,
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                "scale=108:192",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ],
            capture_output=True,
            check=True,
            timeout=30,
        )
        frames.append(result.stdout)
    assert frames[0] != frames[1]
    assert len(frames[0]) == 108 * 192 * 3
    assert frames[0][:3] != b"\0\0\0"


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is unavailable"
)
def test_two_visual_beats_keep_exact_frames_and_source_media(tmp_path: Path) -> None:
    project_id, store, inputs = fixture_project(tmp_path)
    directory = inputs.project_directory
    narration = inputs.narration.model_copy(update={"duration_seconds": 10.0})
    (directory / "narration.json").write_text(narration.model_dump_json(), encoding="utf-8")
    audio = BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 160000)
    (directory / "narration.wav").write_bytes(audio.getvalue())
    first, second = inputs.timed_scene_plan.scenes
    timed = TimedScenePlan.model_validate(
        inputs.timed_scene_plan.model_dump()
        | {
            "narration_duration_seconds": 10,
            "total_duration_seconds": 10,
            "scenes": [
                first.model_dump() | {"end_seconds": 9, "duration_seconds": 9},
                second.model_dump() | {"start_seconds": 9, "end_seconds": 10},
            ],
        }
    )
    (directory / "timed-scenes.json").write_text(timed.model_dump_json(), encoding="utf-8")
    image = Image.new("RGB", (64, 96), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 12, 46, 67), fill="black")
    draw.ellipse((25, 45, 59, 88), fill="red")
    image.save(directory / inputs.visual_assets.assets[0].file_path)
    sources = (
        "narration.json",
        "narration.wav",
        "timed-scenes.json",
        "visual-assets.json",
        "assets/scene-01.png",
        "assets/scene-02.png",
    )
    before = {name: (directory / name).read_bytes() for name in sources}
    channel = load_channel_config("engineering-es")
    artifact = RenderProjectUseCase(
        store,
        FFmpegRenderer(),
        channel.render,
        visual_motion=channel.visual_motion,
        visual_pacing=channel.visual_pacing,
    ).execute(project_id)
    assert (artifact.width, artifact.height, artifact.frame_rate) == (1080, 1920, 30)
    assert (artifact.video_codec, artifact.audio_codec, artifact.pixel_format) == (
        "h264",
        "aac",
        "yuv420p",
    )
    assert abs(artifact.duration_seconds - 10) <= 2 / 30
    assert before == {name: (directory / name).read_bytes() for name in sources}
    pacing = VisualPacingPlan.model_validate_json(
        (directory / "visual-pacing.json").read_text("utf-8")
    )
    assert [len(scene.beats) for scene in pacing.scenes] == [2, 1]
    assert [beat.frame_count for beat in pacing.scenes[0].beats] in (
        [122, 148],
        [135, 135],
        [148, 122],
    )
    assert pacing.scenes[0].beats[-1].end_frame == 270
    video = directory / "render/short.mp4"
    probe = subprocess.run(
        [
            shutil.which("ffprobe") or "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert int(probe.stdout.strip()) == 300
    boundary = pacing.scenes[0].beats[0].end_frame
    samples = []
    for frame in (60, boundary - 1, boundary, 210):
        result = subprocess.run(
            [
                shutil.which("ffmpeg") or "ffmpeg",
                "-v",
                "error",
                "-ss",
                f"{(frame + 0.1) / 30:.6f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                "scale=108:192",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ],
            capture_output=True,
            check=True,
            timeout=30,
        )
        samples.append(Image.frombytes("RGB", (108, 192), result.stdout))
    assert all(sum(ImageStat.Stat(frame).mean) > 30 for frame in samples)
    difference = ImageChops.difference(samples[0], samples[-1])
    assert sum(ImageStat.Stat(difference).mean) > 3
