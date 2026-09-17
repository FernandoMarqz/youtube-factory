"""Provider-neutral paid video and local media-inspection boundaries."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class VideoGenerationRequest:
    scene_sequence: int
    reference_image: Path
    prompt: str
    model: str
    duration_seconds: int
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class GeneratedVideo:
    video_bytes: bytes
    task_id: str
    requested_at: datetime
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class VideoMediaInfo:
    duration_seconds: float
    width: int
    height: int
    fps: float
    video_codec: str
    has_audio: bool


class VideoAssetProvider(Protocol):
    provider: str

    def generate(self, request: VideoGenerationRequest) -> GeneratedVideo:
        """Generate exactly one clip from a prepared reference image."""


class VideoMediaInspector(Protocol):
    def inspect(self, path: Path) -> VideoMediaInfo:
        """Inspect a downloaded clip without trusting its file extension."""
