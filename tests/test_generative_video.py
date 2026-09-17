"""Selective video planning, explicit provider boundary, and offline hybrid rendering."""

import shutil
import subprocess
import sys
import types
import wave
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageStat
from pydantic import ValidationError

from youtube_factory.adapters.ffmpeg import FFmpegRenderer
from youtube_factory.adapters.ffmpeg.video_probe import FFprobeVideoInspector
from youtube_factory.adapters.local import FileSystemArtifactStore
from youtube_factory.adapters.local.fixture_video import LocalFixtureVideoAssetProvider
from youtube_factory.adapters.runway import RunwayVideoAssetProvider
from youtube_factory.application.config import (
    GenerativeVideoConfig,
    load_channel_config,
)
from youtube_factory.application.exceptions import GenerativeVideoError
from youtube_factory.application.services.generative_video import GenerativeVideoEligibilityPolicy
from youtube_factory.application.services.visual_motion import DeterministicVisualMotionPlanner
from youtube_factory.application.services.visual_pacing import DeterministicVisualPacingPlanner
from youtube_factory.application.use_cases import GenerateVideoAssetsUseCase, RenderProjectUseCase
from youtube_factory.domain.enums import AssetType
from youtube_factory.domain.models import (
    ContentManifest,
    GenerativeVideoPlan,
    Narration,
    ResearchProviderMetadata,
    Scene,
    ScenePlan,
    ScriptGeneratorMetadata,
    TimedScenePlan,
    VisualAsset,
    VisualAssetManifest,
)
from youtube_factory.ports.video_assets import GeneratedVideo, VideoGenerationRequest


def _plans(
    durations: tuple[float, ...],
    kinds: tuple[AssetType, ...],
) -> tuple[ScenePlan, TimedScenePlan, VisualAssetManifest]:
    topic_id = uuid4()
    scenes = []
    assets = []
    cursor = 0.0
    for sequence, (duration, kind) in enumerate(zip(durations, kinds, strict=True), 1):
        description = (
            "Animación: ventana cuadrada se transforma en redondeada, grieta detenida"
            if sequence == len(durations)
            else "Presión cambia y el metal se expande"
        )
        scenes.append(
            Scene(
                sequence=sequence,
                narration_segment="La geometría cambia.",
                start_seconds=cursor,
                end_seconds=cursor + duration,
                duration_seconds=duration,
                visual_description=description,
                visual_intent="Mostrar transformación y distribución de fuerzas",
                asset_type=kind,
            )
        )
        assets.append(
            VisualAsset(
                scene_sequence=sequence,
                provider="fixture",
                file_path=f"assets/scene-{sequence:02d}.png",
                width=128,
                height=192,
                prompt_sha256="a" * 64,
            )
        )
        cursor += duration
    semantic = ScenePlan(topic_id=topic_id, scenes=scenes, total_duration_seconds=cursor)
    timed = TimedScenePlan(
        topic_id=topic_id,
        source_total_duration_seconds=cursor,
        narration_duration_seconds=cursor,
        total_duration_seconds=cursor,
        reconciliation_strategy="fixture",
        scenes=scenes,
    )
    visuals = VisualAssetManifest(
        topic_id=topic_id, channel_id="engineering-es", provider="fixture", assets=assets
    )
    return semantic, timed, visuals


def _plan(
    durations: tuple[float, ...],
    kinds: tuple[AssetType, ...],
) -> tuple[ScenePlan, TimedScenePlan, VisualAssetManifest, GenerativeVideoPlan]:
    semantic, timed, visuals = _plans(durations, kinds)
    channel = load_channel_config("engineering-es")
    motion = DeterministicVisualMotionPlanner().plan(
        timed, visuals, channel.visual_motion, channel.render.fps
    )
    pacing = DeterministicVisualPacingPlanner().plan(
        timed, motion, visuals, channel.visual_pacing, channel.visual_motion
    )
    config = channel.generative_video
    plan = GenerativeVideoEligibilityPolicy().plan(timed, semantic, visuals, pacing, config)
    return semantic, timed, visuals, plan


def test_video_config_is_gated_and_validated() -> None:
    config = load_channel_config("engineering-es").generative_video
    assert not config.enabled and config.model == "gen4.5"
    with pytest.raises(ValidationError):
        config.enabled = True
    for changes in (
        {"budget": {"max_generated_scenes": 2, "max_generated_seconds": 5}},
        {"budget": {"max_generated_scenes": 1, "max_generated_seconds": 0}, "enabled": True},
        {"minimum_scene_duration_seconds": -1},
        {"provider": "unknown"},
    ):
        with pytest.raises(ValidationError):
            GenerativeVideoConfig.model_validate(config.model_dump() | changes)


def test_animation_eligibility_budget_and_prompt_are_deterministic() -> None:
    _, _, _, plan = _plan(
        (4.0, 7.0, 9.0),
        (AssetType.IMAGE, AssetType.ANIMATION, AssetType.ANIMATION),
    )
    assert not plan.scenes[0].eligible
    assert plan.scenes[1].eligible and not plan.scenes[1].selected
    assert plan.scenes[2].selected and plan.scenes[2].target_duration_seconds == 5
    assert "transformation" in plan.scenes[2].reasons
    assert "No new text" in (plan.scenes[2].prompt or "")
    assert sum(scene.selected for scene in plan.scenes) == 1
    _, _, _, again = _plan(
        (4.0, 7.0, 9.0), (AssetType.IMAGE, AssetType.ANIMATION, AssetType.ANIMATION)
    )
    assert [scene.scene_sequence for scene in plan.scenes if scene.selected] == [
        scene.scene_sequence for scene in again.scenes if scene.selected
    ]


def test_short_animation_and_diagram_are_not_eligible() -> None:
    _, _, _, plan = _plan(
        (4.0, 7.0, 9.0), (AssetType.ANIMATION, AssetType.DIAGRAM, AssetType.IMAGE)
    )
    assert not any(scene.selected for scene in plan.scenes)


def test_runway_adapter_uses_one_sdk_task_and_data_uri(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from datetime import UTC, datetime

    from youtube_factory.ports.video_assets import VideoGenerationRequest

    reference = tmp_path / "reference.jpg"
    reference.write_bytes(b"jpeg")
    calls: list[dict[str, object]] = []

    class Task:
        id = "task-123"

        def wait_for_task_output(self, *, timeout: int) -> object:
            assert timeout == 900
            return types.SimpleNamespace(output=["https://example.test/clip.mp4"])

    class Client:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["max_retries"] == 0
            self.image_to_video = self

        def create(self, **kwargs: object) -> Task:
            calls.append(kwargs)
            return Task()

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, limit: int) -> bytes:
            return b"video"

    monkeypatch.setitem(sys.modules, "runwayml", types.SimpleNamespace(RunwayML=Client))
    monkeypatch.setattr(
        "youtube_factory.adapters.runway.video_assets.urlopen", lambda *args, **kwargs: Response()
    )
    request = VideoGenerationRequest(7, reference, "Animate", "gen4.5", 5, 900)
    result = RunwayVideoAssetProvider("secret").generate(request)
    assert result.task_id == "task-123" and result.video_bytes == b"video"
    assert len(calls) == 1 and calls[0]["duration"] == 5
    assert str(calls[0]["prompt_image"]).startswith("data:image/jpeg;base64,")
    assert result.completed_at >= result.requested_at >= datetime(2026, 1, 1, tzinfo=UTC)


def _project(tmp_path: Path) -> tuple[str, FileSystemArtifactStore]:
    semantic, timed, visuals = _plans((9.0,), (AssetType.ANIMATION,))
    project_id = str(timed.topic_id)
    directory = tmp_path / project_id
    (directory / "assets").mkdir(parents=True)
    image = Image.new("RGB", (128, 192), (30, 60, 90))
    draw = ImageDraw.Draw(image)
    draw.rectangle((15, 15, 80, 90), fill=(240, 120, 40))
    image.save(directory / "assets" / "scene-01.png")
    audio = BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 144000)
    (directory / "narration.wav").write_bytes(audio.getvalue())
    narration = Narration(
        topic_id=timed.topic_id,
        file_path="narration.wav",
        duration_seconds=9,
        provider="fixture",
        voice="fixture",
        sample_rate_hz=16000,
        narration_text="La geometría cambia.",
        script_sha256="b" * 64,
    )
    manifest = ContentManifest(
        project_id=timed.topic_id,
        pipeline_version="fixture",
        channel_id="engineering-es",
        topic="fixture",
        topic_id=timed.topic_id,
        artifacts=("manifest.json",),
        research_provider=ResearchProviderMetadata(provider="fixture", identifier="fixture"),
        script_generator=ScriptGeneratorMetadata(provider="fixture", identifier="fixture"),
    )
    for filename, model in (
        ("scenes.json", semantic),
        ("timed-scenes.json", timed),
        ("visual-assets.json", visuals),
        ("narration.json", narration),
        ("manifest.json", manifest),
    ):
        (directory / filename).write_text(model.model_dump_json(), encoding="utf-8")
    return project_id, FileSystemArtifactStore(tmp_path)


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg unavailable"
)
def test_fixture_generation_reuse_and_hybrid_render(tmp_path: Path) -> None:
    project_id, store = _project(tmp_path)
    channel = load_channel_config("engineering-es")
    config = channel.generative_video.model_copy(
        update={"enabled": True, "provider": "local-fixture"}
    )
    inspector = FFprobeVideoInspector()
    generator = GenerateVideoAssetsUseCase(
        store,
        config,
        channel.visual_motion,
        channel.visual_pacing,
        30,
        inspector,
        LocalFixtureVideoAssetProvider(),
    )
    plan = generator.execute(project_id, dry_run=True)
    assert plan.scenes[0].selected
    assert store.load_generated_videos(project_id) is None
    generator.execute(project_id, dry_run=False)
    generated = store.load_generated_videos(project_id)
    assert generated is not None and len(generated.assets) == 1
    asset = generated.assets[0]
    assert asset.requested_seconds == 5 and not asset.has_audio
    source = tmp_path / project_id / asset.source_image
    reference = tmp_path / project_id / asset.reference_image
    assert Image.open(reference).size == (720, 1280)
    assert source.read_bytes() != reference.read_bytes()
    before = (tmp_path / project_id / asset.file_path).stat().st_mtime_ns
    generator.execute(project_id, dry_run=False)
    assert (tmp_path / project_id / asset.file_path).stat().st_mtime_ns == before
    # A provider clip may include audio; the final render must map project audio only.
    clip = tmp_path / project_id / asset.file_path
    with_audio = tmp_path / "provider-with-audio.mp4"
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(clip),
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=5",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(with_audio),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    with_audio.replace(clip)
    assert inspector.inspect(clip).has_audio
    renderer = FFmpegRenderer()
    artifact = RenderProjectUseCase(
        store,
        renderer,
        channel.render,
        visual_motion=channel.visual_motion,
        visual_pacing=channel.visual_pacing,
        video_inspector=inspector,
    ).execute(project_id)
    assert artifact.width == 1080 and artifact.height == 1920
    assert artifact.video_codec == "h264" and artifact.audio_codec == "aac"
    assert abs(artifact.duration_seconds - 9) <= 2 / 30
    assert artifact.pixel_format == "yuv420p" and artifact.frame_rate == 30
    assert artifact.audio_mix is not None and artifact.audio_mix.final_integrated_lufs is None
    final = tmp_path / project_id / artifact.file_path
    frames = []
    for second in (2.0, 7.0):
        frame = tmp_path / f"frame-{second}.png"
        subprocess.run(
            [
                shutil.which("ffmpeg") or "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(second),
                "-i",
                str(final),
                "-frames:v",
                "1",
                str(frame),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        frames.append(Image.open(frame).convert("RGB"))
    difference = ImageStat.Stat(ImageChops.difference(*frames)).mean
    assert max(difference) > 1.0
    # A missing clip never triggers provider generation during offline rendering.
    (tmp_path / project_id / asset.file_path).unlink()
    fallback = RenderProjectUseCase(
        store,
        renderer,
        channel.render,
        visual_motion=channel.visual_motion,
        visual_pacing=channel.visual_pacing,
        video_inspector=inspector,
    ).execute(project_id)
    assert abs(fallback.duration_seconds - 9) <= 2 / 30


def test_invalid_download_does_not_replace_existing_clip(tmp_path: Path) -> None:
    project_id, store = _project(tmp_path)
    channel = load_channel_config("engineering-es")
    config = channel.generative_video.model_copy(
        update={"enabled": True, "provider": "local-fixture"}
    )

    class BadProvider:
        provider = "local-fixture"

        def generate(self, request: VideoGenerationRequest) -> GeneratedVideo:
            from datetime import UTC, datetime

            now = datetime.now(UTC)
            return GeneratedVideo(b"not a video", "bad", now, now)

    use_case = GenerateVideoAssetsUseCase(
        store,
        config,
        channel.visual_motion,
        channel.visual_pacing,
        30,
        FFprobeVideoInspector(),
        BadProvider(),
    )
    if shutil.which("ffprobe"):
        with pytest.raises(GenerativeVideoError):
            use_case.execute(project_id, dry_run=False)
        assert store.load_generated_videos(project_id) is None
