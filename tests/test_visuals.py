"""Offline tests for visual prompting and local/OpenAI image adapters."""

import base64
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError

from youtube_factory.adapters.local import (
    LocalNarrationGenerator,
    LocalPlaceholderVisualAssetProvider,
    LocalResearchProvider,
    LocalScenePlanner,
    LocalScriptGenerator,
)
from youtube_factory.adapters.openai import OpenAIVisualAssetProvider, OpenAIVisualConfig
from youtube_factory.adapters.openai.visual_assets import map_openai_image_size
from youtube_factory.application.config import load_channel_config
from youtube_factory.application.exceptions import (
    VisualAssetGenerationError,
    VisualAssetValidationError,
)
from youtube_factory.application.services import (
    DeterministicVisualPromptBuilder,
    SceneTimingReconciler,
)
from youtube_factory.domain.enums import AssetType
from youtube_factory.domain.models import TimedScenePlan, Topic, VisualPrompt, VisualPromptPlan


def make_timed_plan() -> TimedScenePlan:
    """Build the existing deterministic timeline without filesystem persistence."""
    topic = Topic(title="¿Por qué las tapas de alcantarilla son redondas?")
    research = LocalResearchProvider().research(topic)
    script = LocalScriptGenerator().generate(topic, research)
    scene_plan = LocalScenePlanner().plan(script)
    narration = LocalNarrationGenerator().generate(script).narration
    return SceneTimingReconciler().reconcile(scene_plan, narration)


def make_prompt(sequence: int = 1) -> VisualPrompt:
    """Return a small provider-neutral prompt suitable for adapter tests."""
    return VisualPrompt(
        scene_sequence=sequence,
        prompt="A clear top-down engineering illustration of a round manhole cover.",
        exclusions="captions and watermarks",
        visual_intent="Establish the geometry",
        asset_type=AssetType.DIAGRAM,
        width=1024,
        height=1536,
        aspect_ratio="9:16",
        style="educational cinematic illustration",
    )


def png_bytes(width: int = 8, height: int = 12) -> bytes:
    """Build a valid in-memory PNG returned by mocked provider SDKs."""
    buffer = BytesIO()
    Image.new("RGB", (width, height), (20, 40, 60)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_prompt_builder_is_ordered_deterministic_and_channel_aware() -> None:
    timed_plan = make_timed_plan()
    channel = load_channel_config("engineering-es")
    builder = DeterministicVisualPromptBuilder()

    first = builder.build(timed_plan, channel)
    second = builder.build(timed_plan, channel)

    assert first == second
    assert len(first.prompts) == len(timed_plan.scenes)
    assert [prompt.scene_sequence for prompt in first.prompts] == list(
        range(1, len(timed_plan.scenes) + 1)
    )
    assert all(channel.visuals.style in prompt.prompt for prompt in first.prompts)
    assert all("Do not include captions" in prompt.prompt for prompt in first.prompts)
    assert all(prompt.width == 1024 and prompt.height == 1536 for prompt in first.prompts)
    assert first.prompts[0].prompt != timed_plan.scenes[0].visual_description


def test_visual_prompt_plan_rejects_blank_and_out_of_order_prompts() -> None:
    prompt = make_prompt(sequence=2)
    with pytest.raises(ValidationError, match="contiguous"):
        VisualPromptPlan(
            topic_id=make_timed_plan().topic_id,
            channel_id="engineering-es",
            prompts=[prompt],
        )
    with pytest.raises(ValidationError):
        VisualPrompt.model_validate(make_prompt().model_dump() | {"prompt": ""})


def test_local_placeholder_is_a_deterministic_valid_png_without_credentials() -> None:
    provider = LocalPlaceholderVisualAssetProvider()
    prompt = make_prompt()

    first = provider.generate(prompt)
    second = provider.generate(prompt)

    assert first == second
    assert first.asset.file_path == "assets/scene-01.png"
    assert first.asset.provider == "local-placeholder"
    assert first.asset.model is None
    assert (first.asset.width, first.asset.height) == (1024, 1536)
    assert first.asset.prompt_sha256 == sha256(prompt.prompt.encode("utf-8")).hexdigest()
    with Image.open(BytesIO(first.image_bytes)) as image:
        assert image.format == "PNG"
        assert image.size == (1024, 1536)


class FakeImages:
    """Records the official SDK boundary and returns configured response data."""

    def __init__(self, data: list[SimpleNamespace]) -> None:
        self.data = data
        self.kwargs: dict[str, object] = {}

    def generate(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(data=self.data)


def test_openai_provider_sends_exact_prompt_and_records_actual_png_metadata() -> None:
    image_bytes = png_bytes(10, 15)
    images = FakeImages(
        [SimpleNamespace(b64_json=base64.b64encode(image_bytes).decode(), revised_prompt=None)]
    )
    client = SimpleNamespace(images=images)
    provider = OpenAIVisualAssetProvider(
        OpenAIVisualConfig(api_key="test-key", model="gpt-image-2"), client=client
    )
    prompt = make_prompt()

    generated = provider.generate(prompt)

    assert images.kwargs == {
        "model": "gpt-image-2",
        "prompt": prompt.prompt,
        "n": 1,
        "output_format": "png",
        "size": "1024x1536",
    }
    assert generated.image_bytes == image_bytes
    assert generated.asset.provider == "openai"
    assert generated.asset.model == "gpt-image-2"
    assert (generated.asset.width, generated.asset.height) == (10, 15)
    assert generated.asset.prompt_sha256 == sha256(prompt.prompt.encode()).hexdigest()


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [(1024, 1536, "1024x1536"), (1600, 900, "1536x1024"), (800, 800, "1024x1024")],
)
def test_openai_size_mapping_preserves_requested_orientation(
    width: int, height: int, expected: str
) -> None:
    assert map_openai_image_size(width, height) == expected


def test_openai_provider_fails_early_without_key() -> None:
    with pytest.raises(VisualAssetGenerationError, match="OPENAI_API_KEY"):
        OpenAIVisualAssetProvider(OpenAIVisualConfig(api_key="", model="gpt-image-2"))


@pytest.mark.parametrize(
    "data",
    [[], [SimpleNamespace(b64_json=None, revised_prompt=None)]],
)
def test_openai_provider_rejects_empty_response(data: list[SimpleNamespace]) -> None:
    provider = OpenAIVisualAssetProvider(
        OpenAIVisualConfig(api_key="test-key", model="gpt-image-2"),
        client=SimpleNamespace(images=FakeImages(data)),
    )
    with pytest.raises(VisualAssetGenerationError, match="empty"):
        provider.generate(make_prompt())


def test_openai_provider_rejects_malformed_image() -> None:
    encoded = base64.b64encode(b"not a png").decode()
    provider = OpenAIVisualAssetProvider(
        OpenAIVisualConfig(api_key="test-key", model="gpt-image-2"),
        client=SimpleNamespace(
            images=FakeImages([SimpleNamespace(b64_json=encoded, revised_prompt=None)])
        ),
    )
    with pytest.raises(VisualAssetValidationError, match="valid PNG"):
        provider.generate(make_prompt())


def test_openai_provider_translates_api_errors() -> None:
    class RateLimitError(Exception):
        pass

    class FailingImages:
        def generate(self, **kwargs: object) -> None:
            raise RateLimitError

    provider = OpenAIVisualAssetProvider(
        OpenAIVisualConfig(api_key="test-key", model="gpt-image-2"),
        client=SimpleNamespace(images=FailingImages()),
    )
    with pytest.raises(VisualAssetGenerationError, match="rate limit"):
        provider.generate(make_prompt())
