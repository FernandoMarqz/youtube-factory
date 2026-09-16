"""Offline render boundary tests and optional real FFmpeg coverage."""

import json
import shutil
import subprocess
import wave
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from pydantic import ValidationError

from youtube_factory.adapters.ffmpeg import FFmpegRenderer
from youtube_factory.adapters.local import FileSystemArtifactStore
from youtube_factory.application.config import RenderConfig, load_channel_config
from youtube_factory.application.exceptions import (
    RenderError,
    RendererUnavailableError,
    RenderValidationError,
)
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
