"""Static-scene MP4 rendering and independent ffprobe verification."""

import json
import math
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from youtube_factory.adapters.ffmpeg.audio import (
    AUDIO_SAMPLE_RATE,
    LOUDNESS_TOLERANCE_LU,
    PEAK_TOLERANCE_DB,
    LoudnessMeasurement,
    analysis_filter,
    audio_filters,
    parse_loudnorm_report,
)
from youtube_factory.application.config import AudioConfig, RenderConfig
from youtube_factory.application.exceptions import (
    AudioProcessingError,
    AudioValidationError,
    MusicAssetError,
    RenderError,
    RendererUnavailableError,
    RenderValidationError,
)
from youtube_factory.domain.models import AudioMixReport, RenderArtifact
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
        if inputs.caption_ass_path is not None:
            ass = inputs.project_directory / inputs.caption_ass_path
            if inputs.caption_ass_path != "captions/captions.ass" or not ass.is_file():
                raise RenderValidationError("caption ASS input is missing or invalid")
        music_path, music_duration = self._music_input(ffprobe, inputs)
        narration_path = inputs.project_directory.resolve() / inputs.narration.file_path
        narration_measurement = self._measure_audio(
            ffmpeg, narration_path, inputs.audio, dual_mono=True
        )
        output = inputs.project_directory.resolve() / RENDER_PATH
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(".short-part.mp4")
        command = self.build_command(
            ffmpeg,
            inputs,
            config,
            temporary,
            narration_measurement=narration_measurement,
            music_path=music_path,
            music_duration_seconds=music_duration,
        )
        try:
            self._run(command, "FFmpeg", cwd=inputs.project_directory)
            artifact = self._probe(ffprobe, temporary, inputs, config)
            final_measurement = self._measure_audio(
                ffmpeg, temporary, inputs.audio, dual_mono=False
            )
            self._validate_audio(inputs, narration_measurement, final_measurement)
            report = AudioMixReport(
                provider=self.provider,
                identifier="ffmpeg-audio-mixer-v1",
                normalization_enabled=inputs.audio.narration.normalize,
                target_lufs=inputs.audio.narration.target_lufs,
                true_peak_limit_db=inputs.audio.narration.true_peak_db,
                narration_input_lufs=narration_measurement.integrated_lufs,
                narration_was_silent=narration_measurement.silent,
                music_enabled=inputs.audio.music.enabled,
                music_file_path=inputs.audio.music.file_path if music_path else None,
                music_gain_db=inputs.audio.music.gain_db if music_path else None,
                music_loop=inputs.audio.music.loop if music_path else None,
                ducking_enabled=bool(music_path and inputs.audio.ducking.enabled),
                final_integrated_lufs=final_measurement.integrated_lufs,
                final_true_peak_db=final_measurement.true_peak_db,
                sample_rate_hz=artifact.audio_sample_rate_hz or AUDIO_SAMPLE_RATE,
                channels=artifact.audio_channels or 2,
            )
            artifact = artifact.model_copy(update={"audio_mix": report})
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
        executable: str,
        inputs: RenderInputs,
        config: RenderConfig,
        output: Path,
        *,
        narration_measurement: LoudnessMeasurement | None = None,
        music_path: Path | None = None,
        music_duration_seconds: float | None = None,
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
            image = inputs.project_directory.resolve() / asset.file_path
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
        command.extend(["-i", str(inputs.project_directory.resolve() / inputs.narration.file_path)])
        music_index = None
        if inputs.audio.music.enabled:
            if music_path is None:
                raise MusicAssetError("enabled music requires a validated local source")
            music_index = audio_index + 1
            if inputs.audio.music.loop:
                command.extend(["-stream_loop", "-1"])
            command.extend(["-i", str(music_path)])
        concat_label = "[precaption]" if inputs.caption_ass_path else "[v]"
        filters.append(f"{''.join(labels)}concat=n={len(scenes)}:v=1:a=0{concat_label}")
        if inputs.caption_ass_path:
            # A fixed project-relative filter path avoids Windows drive/space escaping.
            filters.append("[precaption]ass=filename=captions/captions.ass[v]")
        filters.extend(
            audio_filters(
                inputs.audio,
                audio_index,
                inputs.narration.duration_seconds,
                narration_measurement,
                music_index,
                music_duration_seconds,
            )
        )
        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[v]",
                "-map",
                "[aout]",
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

    def _run(self, command: list[str], stage: str, cwd: Path | None = None) -> str:
        return self._run_capture(command, stage, cwd).stdout

    def _run_capture(
        self, command: list[str], stage: str, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired as error:
            raise RenderError(f"{stage} timed out after {self._timeout_seconds} seconds") from error
        except OSError as error:
            raise RenderError(f"{stage} could not start: {error}") from error
        if result.returncode != 0:
            detail = result.stderr.strip()[-2000:]
            raise RenderError(f"{stage} failed (exit {result.returncode}): {detail}")
        return result

    def _music_input(self, ffprobe: str, inputs: RenderInputs) -> tuple[Path | None, float | None]:
        music = inputs.audio.music
        if not music.enabled:
            return None, None
        if not music.file_path:
            raise MusicAssetError("enabled music requires a file_path")
        directory = inputs.project_directory.resolve()
        path = (directory / music.file_path).resolve()
        if not path.is_relative_to(directory) or not path.is_file():
            raise MusicAssetError(
                f"music file is missing or outside the project: {music.file_path}"
            )
        try:
            raw = self._run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration:stream=codec_type",
                    "-of",
                    "json",
                    str(path),
                ],
                "music ffprobe",
            )
            probe = json.loads(raw)
            if not any(stream.get("codec_type") == "audio" for stream in probe["streams"]):
                raise ValueError("no audio stream")
            duration = float(probe["format"]["duration"])
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError("invalid duration")
        except (RenderError, ValueError, KeyError, TypeError) as error:
            raise MusicAssetError(
                f"music file has no valid audio stream: {music.file_path}; {str(error)[-300:]}"
            ) from error
        return path, duration

    def _measure_audio(
        self, ffmpeg: str, path: Path, config: AudioConfig, *, dual_mono: bool
    ) -> LoudnessMeasurement:
        command = [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-loglevel",
            "info",
            "-i",
            str(path),
            "-vn",
            "-af",
            analysis_filter(config, dual_mono=dual_mono),
            "-f",
            "null",
            "-",
        ]
        try:
            result = self._run_capture(command, "loudnorm analysis")
            return parse_loudnorm_report(result.stderr)
        except RenderError as error:
            raise AudioProcessingError(f"loudnorm analysis failed: {error}") from error

    @staticmethod
    def _validate_audio(
        inputs: RenderInputs,
        narration: LoudnessMeasurement,
        final: LoudnessMeasurement,
    ) -> None:
        peak = final.true_peak_db
        target = inputs.audio.narration
        if not narration.silent and final.silent:
            raise AudioValidationError("final audio is silent despite audible narration")
        if not final.silent and peak is not None and peak > target.true_peak_db + PEAK_TOLERANCE_DB:
            raise AudioValidationError(
                f"final true peak {peak:.2f} dBTP exceeds {target.true_peak_db:.2f} dBTP"
            )
        if target.normalize and not narration.silent:
            measured = final.integrated_lufs
            if measured is None or abs(measured - target.target_lufs) > LOUDNESS_TOLERANCE_LU:
                raise AudioValidationError(
                    "final integrated loudness is outside the configured target: "
                    f"measured={measured}, target={target.target_lufs}, "
                    f"tolerance={LOUDNESS_TOLERANCE_LU} LU"
                )

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
                "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,"
                "pix_fmt,sample_rate,channels",
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
            sample_rate = int(audio["sample_rate"])
            channels = int(audio["channels"])
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
            or sample_rate != AUDIO_SAMPLE_RATE
            or channels != 2
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
            audio_sample_rate_hz=sample_rate,
            audio_channels=channels,
        )
