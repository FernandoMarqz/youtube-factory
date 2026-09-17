"""Offline contract fixture; this is not a generative-video substitute."""

import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from youtube_factory.application.exceptions import GenerativeVideoError
from youtube_factory.ports.video_assets import GeneratedVideo, VideoGenerationRequest


class LocalFixtureVideoAssetProvider:
    provider = "local-fixture"

    def generate(self, request: VideoGenerationRequest) -> GeneratedVideo:
        executable = shutil.which("ffmpeg")
        if not executable:
            raise GenerativeVideoError("ffmpeg executable not found for local fixture")
        started = datetime.now(UTC)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "fixture.mp4"
            command = [
                executable,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-loop",
                "1",
                "-framerate",
                "30",
                "-i",
                str(request.reference_image),
                "-t",
                str(request.duration_seconds),
                "-vf",
                "scale=720:1280,format=yuv420p",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                str(output),
            ]
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=request.timeout_seconds,
                )
                data = output.read_bytes()
            except (OSError, subprocess.SubprocessError) as error:
                raise GenerativeVideoError("local fixture video generation failed") from error
        return GeneratedVideo(
            video_bytes=data,
            task_id=f"local-fixture-scene-{request.scene_sequence}",
            requested_at=started,
            completed_at=datetime.now(UTC),
        )
