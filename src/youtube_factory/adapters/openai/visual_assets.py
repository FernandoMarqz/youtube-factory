"""OpenAI Images adapter isolated behind the visual asset provider port."""

import base64
import binascii
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from youtube_factory.application.exceptions import (
    VisualAssetGenerationError,
    VisualAssetValidationError,
)
from youtube_factory.application.services.png import validate_png
from youtube_factory.domain.models import VisualAsset, VisualPrompt
from youtube_factory.ports import GeneratedVisualAsset

_OPENAI_SIZES = ((1024, 1024), (1536, 1024), (1024, 1536))


@dataclass(frozen=True, slots=True)
class OpenAIVisualConfig:
    """Explicit OpenAI image settings assembled by the composition root."""

    api_key: str
    model: str


class OpenAIVisualAssetProvider:
    """Generates provider-neutral PNG assets with the official OpenAI SDK."""

    identifier = "openai"
    model: str | None

    def __init__(self, config: OpenAIVisualConfig, client: Any | None = None) -> None:
        if not config.api_key.strip():
            raise VisualAssetGenerationError("OPENAI_API_KEY is required for OpenAI visuals")
        if not config.model.strip():
            raise VisualAssetGenerationError("OpenAI visual model is required")
        self._config = config
        self.model = config.model
        self._client = client if client is not None else _create_openai_client(config.api_key)

    def generate(self, prompt: VisualPrompt) -> GeneratedVisualAsset:
        """Request one PNG, decode it, and record its actual media dimensions."""
        size = map_openai_image_size(prompt.width, prompt.height)
        try:
            response = self._client.images.generate(
                model=self._config.model,
                prompt=prompt.prompt,
                n=1,
                output_format="png",
                size=size,
            )
            data = response.data
            encoded = data[0].b64_json if data else None
            revised_prompt = data[0].revised_prompt if data else None
        except Exception as error:
            raise VisualAssetGenerationError(_openai_error_message(error)) from error
        if not encoded:
            raise VisualAssetGenerationError("OpenAI returned an empty visual asset")
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError, binascii.Error) as error:
            raise VisualAssetValidationError("OpenAI returned malformed image data") from error
        width, height = validate_png(image_bytes)
        asset = VisualAsset(
            scene_sequence=prompt.scene_sequence,
            provider=self.identifier,
            model=self.model,
            file_path=f"assets/scene-{prompt.scene_sequence:02d}.png",
            width=width,
            height=height,
            media_type="image/png",
            prompt_sha256=sha256(prompt.prompt.encode("utf-8")).hexdigest(),
            revised_prompt=revised_prompt,
        )
        return GeneratedVisualAsset(asset=asset, image_bytes=image_bytes)


def map_openai_image_size(width: int, height: int) -> str:
    """Map provider-neutral dimensions to the closest supported OpenAI orientation size."""
    requested_ratio = width / height
    selected = min(_OPENAI_SIZES, key=lambda size: abs((size[0] / size[1]) - requested_ratio))
    return f"{selected[0]}x{selected[1]}"


def _create_openai_client(api_key: str) -> Any:
    try:
        from openai import OpenAI
    except ImportError as error:
        raise VisualAssetGenerationError("OpenAI SDK is not installed") from error
    return OpenAI(api_key=api_key)


def _openai_error_message(error: Exception) -> str:
    error_name = type(error).__name__
    if error_name == "AuthenticationError":
        return "OpenAI authentication failed"
    if error_name == "RateLimitError":
        return "OpenAI rate limit reached"
    if error_name in {"APIConnectionError", "APITimeoutError"}:
        return "OpenAI visual service is unavailable"
    return "OpenAI visual request failed"
