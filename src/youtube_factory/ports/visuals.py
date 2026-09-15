"""Provider-neutral visual asset generation boundary."""

from dataclasses import dataclass
from typing import Protocol

from youtube_factory.domain.models import VisualAsset, VisualPrompt


@dataclass(frozen=True, slots=True)
class GeneratedVisualAsset:
    """Validated visual metadata plus image bytes awaiting persistence."""

    asset: VisualAsset
    image_bytes: bytes

    def __post_init__(self) -> None:
        """Reject an empty binary before it reaches infrastructure."""
        if not self.image_bytes:
            raise ValueError("generated visual image must not be empty")


class VisualAssetProvider(Protocol):
    """Generates one visual asset from one provider-ready prompt."""

    identifier: str
    model: str | None

    def generate(self, prompt: VisualPrompt) -> GeneratedVisualAsset:
        """Generate one image and provider-neutral metadata."""
