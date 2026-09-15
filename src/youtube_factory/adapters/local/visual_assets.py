"""Deterministic PNG placeholders for offline visual pipeline development."""

from hashlib import sha256
from io import BytesIO

from PIL import Image, ImageDraw

from youtube_factory.application.services.png import validate_png
from youtube_factory.domain.models import VisualAsset, VisualPrompt
from youtube_factory.ports import GeneratedVisualAsset


class LocalPlaceholderVisualAssetProvider:
    """Creates one inspectable, deterministic card for every visual prompt."""

    identifier = "local-placeholder"
    model: str | None = None

    def generate(self, prompt: VisualPrompt) -> GeneratedVisualAsset:
        """Render a real PNG matching the prompt's requested dimensions."""
        image = Image.new("RGB", (prompt.width, prompt.height), color=(18, 32, 51))
        draw = ImageDraw.Draw(image)
        margin = max(24, prompt.width // 16)
        accent = (40 + (prompt.scene_sequence * 29) % 160, 164, 196)
        draw.rounded_rectangle(
            (margin, margin, prompt.width - margin, prompt.height - margin),
            radius=max(16, prompt.width // 32),
            outline=accent,
            width=max(4, prompt.width // 128),
        )
        label = f"SCENE {prompt.scene_sequence:02d}"
        box = draw.textbbox((0, 0), label)
        label_width = box[2] - box[0]
        draw.text(
            ((prompt.width - label_width) // 2, prompt.height // 2),
            label,
            fill=(238, 245, 250),
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG", compress_level=9)
        image_bytes = buffer.getvalue()
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
        )
        return GeneratedVisualAsset(asset=asset, image_bytes=image_bytes)
