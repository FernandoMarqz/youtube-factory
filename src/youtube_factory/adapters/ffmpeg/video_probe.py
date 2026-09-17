"""Validate optional generated clips independently from final MP4 validation."""

import json
import math
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from youtube_factory.application.exceptions import GenerativeVideoError
from youtube_factory.ports.video_assets import VideoMediaInfo


class FFprobeVideoInspector:
    def inspect(self, path: Path) -> VideoMediaInfo:
        executable = shutil.which("ffprobe")
        if not executable:
            raise GenerativeVideoError("ffprobe executable not found")
        if not path.is_file() or path.stat().st_size == 0:
            raise GenerativeVideoError(f"generated video is missing or empty: {path.name}")
        try:
            result = subprocess.run(
                [
                    executable,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
                    "-of",
                    "json",
                    str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            payload = json.loads(result.stdout)
            video = next(
                stream for stream in payload["streams"] if stream.get("codec_type") == "video"
            )
            info = VideoMediaInfo(
                duration_seconds=float(payload["format"]["duration"]),
                width=int(video["width"]),
                height=int(video["height"]),
                fps=float(Fraction(video["avg_frame_rate"])),
                video_codec=str(video["codec_name"]),
                has_audio=any(stream.get("codec_type") == "audio" for stream in payload["streams"]),
            )
        except (
            OSError,
            subprocess.SubprocessError,
            ValueError,
            KeyError,
            StopIteration,
            TypeError,
            ZeroDivisionError,
        ) as error:
            raise GenerativeVideoError(f"generated video failed ffprobe: {path.name}") from error
        if (
            not math.isfinite(info.duration_seconds)
            or info.duration_seconds <= 0
            or info.width < 16
            or info.height < 16
            or not math.isfinite(info.fps)
            or info.fps <= 0
            or not info.video_codec
        ):
            raise GenerativeVideoError(f"generated video has invalid media metadata: {path.name}")
        return info
