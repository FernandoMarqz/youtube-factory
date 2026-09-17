"""Runway Gen-4.5 image-to-video using the official Python SDK."""

import base64
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

from youtube_factory.application.exceptions import (
    GenerativeVideoConfigurationError,
    GenerativeVideoError,
)
from youtube_factory.ports.video_assets import GeneratedVideo, VideoGenerationRequest


class RunwayVideoAssetProvider:
    provider = "runway"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise GenerativeVideoConfigurationError("RUNWAYML_API_SECRET is required")
        self._api_key = api_key

    def generate(self, request: VideoGenerationRequest) -> GeneratedVideo:
        try:
            from runwayml import RunwayML  # type: ignore[import-not-found]
        except ImportError as error:
            raise GenerativeVideoConfigurationError(
                "Runway SDK is missing; install the 'runway' optional dependency"
            ) from error
        image = request.reference_image.read_bytes()
        data_uri = "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")
        if len(data_uri.encode("ascii")) > 5_000_000:
            raise GenerativeVideoError("reference image exceeds Runway's 5 MB data URI limit")
        started = datetime.now(UTC)
        task_id: str | None = None
        try:
            # Disable SDK retries: one CLI invocation must submit at most one paid task.
            client = RunwayML(api_key=self._api_key, max_retries=0, timeout=60.0)
            task: Any = client.image_to_video.create(
                model=request.model,
                prompt_image=data_uri,
                prompt_text=request.prompt,
                ratio="720:1280",
                duration=request.duration_seconds,
            )
            task_id = str(task.id)
            completed: Any = task.wait_for_task_output(timeout=request.timeout_seconds)
            output = completed.output
            if not output or not isinstance(output[0], str):
                raise GenerativeVideoError(f"Runway task {task_id} returned no video URL")
            url = output[0]
            if urlparse(url).scheme != "https":
                raise GenerativeVideoError("Runway returned a non-HTTPS video URL")
            with urlopen(url, timeout=120) as response:
                video = response.read(200_000_001)
            if not video or len(video) > 200_000_000:
                raise GenerativeVideoError("Runway video download is empty or exceeds 200 MB")
        except GenerativeVideoError:
            raise
        except Exception as error:
            status = getattr(error, "status_code", None)
            raise GenerativeVideoError(
                f"Runway image-to-video task {task_id or 'not submitted'} failed: "
                f"{type(error).__name__}" + (f" (HTTP {status})" if isinstance(status, int) else "")
            ) from error
        return GeneratedVideo(
            video_bytes=video,
            task_id=task_id,
            requested_at=started,
            completed_at=datetime.now(UTC),
        )
