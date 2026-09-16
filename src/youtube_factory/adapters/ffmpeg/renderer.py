"""Static-scene MP4 rendering and independent ffprobe verification."""

import json
import math
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from youtube_factory.application.config import RenderConfig
from youtube_factory.application.exceptions import (
    RenderError,
    RendererUnavailableError,
    RenderValidationError,
)
from youtube_factory.domain.models import RenderArtifact
from youtube_factory.ports import RenderInputs

RENDER_PATH = "render/short.mp4"


class FFmpegRenderer:
    """Render static PNG scenes at authoritative frame boundaries with hard cuts."""

    provider = "ffmpeg"
    identifier = "ffmpeg-renderer-v1"

    def __init__(self, timeout_seconds: int = 600) -> None:
        self._timeout_seconds = timeout_seconds

    def check_available(self) -> None:
        """Fail before upstream provider calls when media executables are missing."""
        self._find_executable("ffmpeg")
        self._find_executable("ffprobe")

    def render(self, inputs: RenderInputs, config: RenderConfig) -> RenderArtifact:
        """Encode the prepared scene images and WAV, then inspect the final MP4."""
        ffmpeg = self._find_executable("ffmpeg")
        ffprobe = self._find_executable("ffprobe")
        output = inputs.project_directory / RENDER_PATH
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(".short-part.mp4")
        command = self.build_command(ffmpeg, inputs, config, temporary)
        try:
            self._run(command, "FFmpeg")
            artifact = self._probe(ffprobe, temporary, inputs, config)
            temporary.replace(output)
            return artifact
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _find_executable(name: str) -> str:
        executable = shutil.which(name)
        if executable is None:
            raise RendererUnavailableError(
                f"{name} executable not found. Install FFmpeg and ensure ffmpeg and ffprobe "
                "are available on PATH."
            )
        return executable

    @staticmethod
    def build_command(
        executable: str, inputs: RenderInputs, config: RenderConfig, output: Path
    ) -> list[str]:
        """Build argument arrays; frame counts come from rounded timed-scene boundaries."""
        command = [executable, "-hide_banner", "-loglevel", "error", "-y"]
        filters: list[str] = []
        labels: list[str] = []
        scenes = inputs.timed_scene_plan.scenes
        if len(scenes) != len(inputs.visual_assets.assets):
            raise RenderValidationError("timed scene and visual asset counts differ")
        for index, (scene, asset) in enumerate(
            zip(scenes, inputs.visual_assets.assets, strict=True)
        ):
            if scene.sequence != asset.scene_sequence:
                raise RenderValidationError("scene and asset sequences do not match")
            image = inputs.project_directory / asset.file_path
            command.extend(["-loop", "1", "-framerate", str(config.fps), "-i", str(image)])
            start_frame = round(scene.start_seconds * config.fps)
            end_frame = round(scene.end_seconds * config.fps)
            frames = end_frame - start_frame
            if frames < 1:
                raise RenderValidationError(f"scene {scene.sequence} is shorter than one frame")
            label = f"v{index}"
            labels.append(f"[{label}]")
            filters.append(
                f"[{index}:v]trim=end_frame={frames},setpts=PTS-STARTPTS,"
                f"scale={config.width}:{config.height}:force_original_aspect_ratio=increase,"
                f"crop={config.width}:{config.height},setsar=1,format={config.pixel_format}"
                f"[{label}]"
            )
        audio_index = len(scenes)
        command.extend(["-i", str(inputs.project_directory / inputs.narration.file_path)])
        filters.append(f"{''.join(labels)}concat=n={len(scenes)}:v=1:a=0[v]")
        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[v]",
                "-map",
                f"{audio_index}:a:0",
                "-c:v",
                config.video_codec,
                "-pix_fmt",
                config.pixel_format,
                "-r",
                str(config.fps),
                "-c:a",
                config.audio_codec,
                "-b:a",
                config.audio_bitrate,
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        return command

    def _run(self, command: list[str], stage: str) -> str:
        try:
            result = subprocess.run(
                command, check=False, capture_output=True, text=True, timeout=self._timeout_seconds
            )
        except subprocess.TimeoutExpired as error:
            raise RenderError(f"{stage} timed out after {self._timeout_seconds} seconds") from error
        except OSError as error:
            raise RenderError(f"{stage} could not start: {error}") from error
        if result.returncode != 0:
            detail = result.stderr.strip()[-2000:]
            raise RenderError(f"{stage} failed (exit {result.returncode}): {detail}")
        return result.stdout

    def _probe(
        self, executable: str, output: Path, inputs: RenderInputs, config: RenderConfig
    ) -> RenderArtifact:
        if not output.is_file() or output.stat().st_size == 0:
            raise RenderValidationError("FFmpeg did not produce a non-empty MP4")
        raw = self._run(
            [
                executable,
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,pix_fmt",
                "-of",
                "json",
                str(output),
            ],
            "ffprobe",
        )
        try:
            probe: dict[str, Any] = json.loads(raw)
            streams = probe["streams"]
            video = next(stream for stream in streams if stream.get("codec_type") == "video")
            audio = next(stream for stream in streams if stream.get("codec_type") == "audio")
            duration = float(probe["format"]["duration"])
            fps = float(Fraction(video["avg_frame_rate"]))
            width = int(video["width"])
            height = int(video["height"])
            video_codec = str(video["codec_name"])
            audio_codec = str(audio["codec_name"])
            pixel_format = str(video["pix_fmt"])
        except (ValueError, KeyError, StopIteration, TypeError, ZeroDivisionError) as error:
            raise RenderValidationError(
                "ffprobe returned invalid video or audio metadata"
            ) from error
        expected_video_codec = "h264" if config.video_codec == "libx264" else config.video_codec
        tolerance = 2 / config.fps
        if (
            width != config.width
            or height != config.height
            or abs(fps - config.fps) > 0.01
            or video_codec != expected_video_codec
            or audio_codec != config.audio_codec
            or pixel_format != config.pixel_format
            or not math.isfinite(duration)
            or duration <= 0
            or not math.isfinite(fps)
            or abs(duration - inputs.timed_scene_plan.total_duration_seconds) > tolerance
        ):
            raise RenderValidationError(
                "rendered media differs from configuration or narration timing"
            )
        return RenderArtifact(
            provider=self.provider,
            file_path=RENDER_PATH,
            duration_seconds=duration,
            width=width,
            height=height,
            frame_rate=fps,
            video_codec=video_codec,
            audio_codec=audio_codec,
            pixel_format=pixel_format,
            file_size_bytes=output.stat().st_size,
        )
