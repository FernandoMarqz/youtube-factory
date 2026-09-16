"""Offline caption contracts, reconciliation, planning, storage and media tests."""

import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_rendering import fixture_project

from youtube_factory.adapters.ffmpeg import FFmpegRenderer
from youtube_factory.adapters.local import LocalCaptionAlignmentProvider
from youtube_factory.adapters.openai import (
    OpenAICaptionAlignmentConfig,
    OpenAICaptionAlignmentProvider,
)
from youtube_factory.application.config import load_channel_config
from youtube_factory.application.exceptions import CaptionAlignmentError
from youtube_factory.application.services.canonical_alignment import reconcile_words
from youtube_factory.application.services.captions import CaptionPlanner, build_ass
from youtube_factory.application.use_cases import CaptionProjectUseCase, RenderProjectUseCase
from youtube_factory.domain.models import AlignedWord, CaptionPlan, Narration, WordAlignment


def narration(text: str = "¿Por qué una junta, cambia?") -> Narration:
    return Narration(
        topic_id=uuid4(),
        file_path="narration.wav",
        duration_seconds=2,
        provider="local",
        voice="fixture",
        sample_rate_hz=16000,
        narration_text=text,
        script_sha256="a" * 64,
    )


def recognized(*tokens: str) -> list[AlignedWord]:
    return [
        AlignedWord(text=token, start_seconds=index * 0.2, end_seconds=(index + 1) * 0.2)
        for index, token in enumerate(tokens)
    ]


def test_word_alignment_contracts() -> None:
    sample = narration()
    words = recognized("Por", "qué")
    WordAlignment(topic_id=sample.topic_id, provider="fixture", duration_seconds=2, words=words)
    for change in ({"start_seconds": -1}, {"end_seconds": 0}):
        with pytest.raises(ValidationError):
            AlignedWord.model_validate(words[0].model_dump() | change)
    with pytest.raises(ValidationError, match="chronological"):
        WordAlignment(
            topic_id=sample.topic_id,
            provider="fixture",
            duration_seconds=2,
            words=list(reversed(words)),
        )
    with pytest.raises(ValidationError, match="exceed narration"):
        WordAlignment(
            topic_id=sample.topic_id, provider="fixture", duration_seconds=0.2, words=words
        )


def test_caption_configuration_is_strict_and_immutable() -> None:
    captions = load_channel_config("engineering-es").captions
    assert captions.enabled and captions.alignment.model == "whisper-1"
    with pytest.raises(ValidationError):
        captions.enabled = False
    for change in (
        {"grouping": captions.grouping.model_dump() | {"max_words_per_cue": 0}},
        {"grouping": captions.grouping.model_dump() | {"max_cue_duration_seconds": 0.1}},
        {"style": captions.style.model_dump() | {"max_lines": 3}},
        {"alignment": {"provider": "unknown"}},
        {"alignment": {"provider": "openai"}},
    ):
        with pytest.raises(ValidationError):
            type(captions).model_validate(captions.model_dump() | change)


def test_canonical_reconciliation_preserves_punctuation_quotes_and_accents() -> None:
    canonical = "¿Por qué la ‘junta,’ cambia?"
    words = reconcile_words(canonical, recognized("Por", "que", "la", "junta", "cambia"))
    assert [word.text for word in words] == canonical.split()
    assert words[0].start_seconds == 0
    assert words[-1].end_seconds == pytest.approx(1)


def test_reconciliation_rejects_poor_match_and_can_bridge_one_missing_word() -> None:
    with pytest.raises(CaptionAlignmentError, match=r"matched .*/4"):
        reconcile_words("uno dos tres cuatro", recognized("other", "unrelated"))
    canonical = "uno dos tres cuatro cinco seis siete ocho nueve diez"
    provider_words = recognized(
        "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "diez"
    )
    provider_words[-1] = AlignedWord(text="diez", start_seconds=1.8, end_seconds=2)
    words = reconcile_words(canonical, provider_words)
    assert [word.text for word in words] == canonical.split()
    assert words[8].start_seconds >= words[7].end_seconds


def test_local_alignment_and_caption_plan_are_deterministic() -> None:
    sample = narration("¿Por qué el acero cambia de longitud? Porque se calienta.")
    provider = LocalCaptionAlignmentProvider()
    first = provider.align(sample, b"unused", "es-ES")
    assert first == provider.align(sample, b"unused", "es-ES")
    assert first.provider == "local-synthetic"
    assert [word.text for word in first.words] == sample.narration_text.split()
    channel = load_channel_config("engineering-es")
    planner = CaptionPlanner()
    plan = planner.plan(first, "es-ES", channel.captions.grouping)
    assert plan == planner.plan(first, "es-ES", channel.captions.grouping)
    assert all(len(cue.text.split()) <= 5 for cue in plan.cues)
    assert " ".join(cue.text for cue in plan.cues) == sample.narration_text
    assert all(
        a.end_seconds <= b.start_seconds for a, b in zip(plan.cues, plan.cues[1:], strict=False)
    )


def test_planner_avoids_a_single_word_after_full_previous_cue() -> None:
    sample = narration("Esa es la razón más práctica: tenga la orientación que tenga.")
    alignment = LocalCaptionAlignmentProvider().align(sample, b"", "es-ES")
    plan = CaptionPlanner().plan(
        alignment, "es-ES", load_channel_config("engineering-es").captions.grouping
    )
    assert all(len(cue.text.split()) > 1 for cue in plan.cues)
    assert " ".join(cue.text for cue in plan.cues) == sample.narration_text


def test_planner_splits_when_total_characters_fit_but_two_lines_cannot() -> None:
    text = "ABCDEFGHIJKLM NOPQRSTUVWXYZ ABCDEFGHIJKLM"
    sample = narration(text)
    alignment = LocalCaptionAlignmentProvider().align(sample, b"", "es-ES")
    config = load_channel_config("engineering-es").captions.grouping

    plan = CaptionPlanner().plan(alignment, "es-ES", config)

    assert len(plan.cues) > 1
    assert " ".join(cue.text for cue in plan.cues) == text
    ass = build_ass(
        plan,
        load_channel_config("engineering-es").captions.style,
        1080,
        1920,
        config.max_characters_per_line,
    )
    dialogue_lines = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert all(
        len(line) <= config.max_characters_per_line
        for dialogue in dialogue_lines
        for line in dialogue.split(",,0,0,0,,", 1)[1].split("\\N")
    )


def test_ass_has_style_unicode_escaping_and_two_line_wrap() -> None:
    sample = narration("¿Por qué {esto} cambia? Porque la temperatura sube.")
    channel = load_channel_config("engineering-es")
    alignment = LocalCaptionAlignmentProvider().align(sample, b"", "es-ES")
    plan = CaptionPlanner().plan(alignment, "es-ES", channel.captions.grouping)
    assert isinstance(plan, CaptionPlan)
    ass = build_ass(plan, channel.captions.style, 1080, 1920, 24)
    assert "[V4+ Styles]" in ass and "PlayResX: 1080" in ass
    assert "Style: Caption,Arial,64" in ass
    assert "450,1" in ass
    assert "¿Por qué" in ass
    assert "\\{esto\\}" in ass
    assert "Dialogue: 0,0:00:00.00" in ass
    assert all(line.count("\\N") <= 1 for line in ass.splitlines() if line.startswith("Dialogue:"))


class FakeTranscriptions:
    def __init__(self, words: list[SimpleNamespace] | None = None, error: Exception | None = None):
        self.words = words
        self.error = error
        self.request: dict[str, object] = {}

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.request = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(words=self.words)


def test_openai_alignment_uses_word_timestamps_and_canonical_text() -> None:
    sample = narration("¿Por qué cambia?")
    fake = FakeTranscriptions(
        [
            SimpleNamespace(word="Por", start=0.1, end=0.3),
            SimpleNamespace(word="que", start=0.3, end=0.5),
            SimpleNamespace(word="cambia", start=0.5, end=0.9),
        ]
    )
    provider = OpenAICaptionAlignmentProvider(
        OpenAICaptionAlignmentConfig("test-key", "whisper-1"),
        SimpleNamespace(audio=SimpleNamespace(transcriptions=fake)),
    )
    result = provider.align(sample, b"RIFFfixture", "es-ES")
    assert [word.text for word in result.words] == sample.narration_text.split()
    assert fake.request == {
        "file": ("narration.wav", b"RIFFfixture", "audio/wav"),
        "model": "whisper-1",
        "language": "es",
        "response_format": "verbose_json",
        "timestamp_granularities": ["word"],
    }


def test_openai_repairs_one_zero_length_word_from_adjacent_interval() -> None:
    sample = narration("El puente cambia temperatura rápido")
    fake = FakeTranscriptions(
        [
            SimpleNamespace(word="El", start=0.0, end=0.2),
            SimpleNamespace(word="puente", start=0.2, end=0.5),
            SimpleNamespace(word="cambia", start=0.5, end=0.7),
            SimpleNamespace(word="temperatura", start=0.7000000476837158, end=0.7000000476837158),
            SimpleNamespace(word="rápido", start=0.7, end=1.0),
        ]
    )
    provider = OpenAICaptionAlignmentProvider(
        OpenAICaptionAlignmentConfig("test-key", "whisper-1"),
        SimpleNamespace(audio=SimpleNamespace(transcriptions=fake)),
    )
    result = provider.align(sample, b"RIFFfixture", "es-ES")
    assert [word.text for word in result.words] == sample.narration_text.split()
    assert result.words[3].start_seconds == pytest.approx(0.7)
    assert 0 < result.words[3].end_seconds - result.words[3].start_seconds <= 0.020001
    assert result.words[3].end_seconds <= result.words[4].start_seconds


def test_openai_repairs_zero_length_word_in_gap_or_at_end() -> None:
    sample = narration("uno dos tres")
    for raw, zero_index in (
        (
            [("uno", 0.0, 0.2), ("dos", 0.2, 0.2), ("tres", 0.3, 0.6)],
            1,
        ),
        (
            [("uno", 0.0, 0.2), ("dos", 0.2, 0.6), ("tres", 0.6, 0.6)],
            2,
        ),
    ):
        fake = FakeTranscriptions(
            [SimpleNamespace(word=text, start=start, end=end) for text, start, end in raw]
        )
        provider = OpenAICaptionAlignmentProvider(
            OpenAICaptionAlignmentConfig("test-key", "whisper-1"),
            SimpleNamespace(audio=SimpleNamespace(transcriptions=fake)),
        )
        result = provider.align(sample, b"RIFFfixture", "es-ES")
        assert result.words[zero_index].end_seconds > result.words[zero_index].start_seconds
        assert [word.text for word in result.words] == ["uno", "dos", "tres"]


def test_duplicate_provider_word_does_not_change_display_text() -> None:
    words = reconcile_words("uno dos tres", recognized("uno", "uno", "dos", "tres"))
    assert [word.text for word in words] == ["uno", "dos", "tres"]


def test_openai_alignment_errors_are_explicit() -> None:
    sample = narration()
    with pytest.raises(CaptionAlignmentError, match="OPENAI_API_KEY"):
        OpenAICaptionAlignmentProvider(OpenAICaptionAlignmentConfig("", "whisper-1"))
    for error, message in (
        (type("AuthenticationError", (Exception,), {})(), "authentication failed"),
        (type("RateLimitError", (Exception,), {})(), "rate limit"),
        (type("APIConnectionError", (Exception,), {})(), "unavailable"),
    ):
        fake = FakeTranscriptions(error=error)
        provider = OpenAICaptionAlignmentProvider(
            OpenAICaptionAlignmentConfig("test", "whisper-1"),
            SimpleNamespace(audio=SimpleNamespace(transcriptions=fake)),
        )
        with pytest.raises(CaptionAlignmentError, match=message):
            provider.align(sample, b"wav", "es-ES")
    for words in ([], [SimpleNamespace(word="x", start=1, end=0)]):
        fake = FakeTranscriptions(words)
        provider = OpenAICaptionAlignmentProvider(
            OpenAICaptionAlignmentConfig("test", "whisper-1"),
            SimpleNamespace(audio=SimpleNamespace(transcriptions=fake)),
        )
        with pytest.raises(CaptionAlignmentError):
            provider.align(sample, b"wav", "es-ES")
    for words in (
        [SimpleNamespace(word="x", start=0.2, end=0.2)],
        [
            SimpleNamespace(word="x", start=0.2, end=0.4),
            SimpleNamespace(word="y", start=0.1, end=0.5),
        ],
    ):
        fake = FakeTranscriptions(words)
        provider = OpenAICaptionAlignmentProvider(
            OpenAICaptionAlignmentConfig("test", "whisper-1"),
            SimpleNamespace(audio=SimpleNamespace(transcriptions=fake)),
        )
        with pytest.raises(CaptionAlignmentError, match="invalid OpenAI word timestamps"):
            provider.align(sample, b"wav", "es-ES")


def test_caption_project_persists_artifacts_and_render_uses_ass(tmp_path: Path) -> None:
    project_id, store, inputs = fixture_project(tmp_path)
    channel = load_channel_config("engineering-es")
    CaptionProjectUseCase(store, LocalCaptionAlignmentProvider(), channel).execute(project_id)
    directory = inputs.project_directory
    assert (directory / "word-alignment.json").is_file()
    assert (directory / "captions.json").is_file()
    assert (directory / "captions/captions.ass").is_file()
    from youtube_factory.domain.models import ContentManifest

    manifest = ContentManifest.model_validate_json((directory / "manifest.json").read_text("utf-8"))
    assert manifest.caption_alignment is not None
    assert manifest.caption_alignment.provider == "local-synthetic"
    assert manifest.caption_planner is not None
    assert manifest.caption_planner.cue_count > 0

    class RecordingRenderer:
        identifier = "fixture"
        provider = "ffmpeg"
        received: object = None

        def render(self, value: object, config: object) -> object:
            from youtube_factory.domain.models import RenderArtifact

            self.received = value
            (directory / "render").mkdir(exist_ok=True)
            (directory / "render/short.mp4").write_bytes(b"fixture")
            return RenderArtifact(
                provider="ffmpeg",
                file_path="render/short.mp4",
                duration_seconds=2,
                width=1080,
                height=1920,
                frame_rate=30,
                video_codec="h264",
                audio_codec="aac",
                pixel_format="yuv420p",
                file_size_bytes=7,
            )

    renderer = RecordingRenderer()
    RenderProjectUseCase(store, renderer, channel.render, channel.captions).execute(project_id)
    assert renderer.received.caption_ass_path == "captions/captions.ass"  # type: ignore[union-attr]
    original_ass = (directory / "captions/captions.ass").read_text("utf-8")
    alignment_before = (directory / "word-alignment.json").read_bytes()
    new_style = channel.captions.style.model_copy(update={"font_size": 72})
    new_captions = channel.captions.model_copy(update={"style": new_style})
    RenderProjectUseCase(store, renderer, channel.render, new_captions).execute(project_id)
    assert (directory / "captions/captions.ass").read_text("utf-8") != original_ass
    assert (directory / "word-alignment.json").read_bytes() == alignment_before


def test_caption_project_cli_uses_persisted_narration_only(tmp_path: Path) -> None:
    project_id, _, inputs = fixture_project(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "youtube_factory",
            "caption-project",
            "--project-id",
            project_id,
            "--channel",
            "engineering-es",
            "--caption-alignment",
            "local",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (inputs.project_directory / "captions.json").is_file()
    assert (inputs.project_directory / "word-alignment.json").is_file()


def test_ass_filter_uses_relative_path_but_media_arguments_are_absolute(tmp_path: Path) -> None:
    project_id, _, inputs = fixture_project(tmp_path / "folder with spaces")
    assert project_id
    command = FFmpegRenderer.build_command(
        "ffmpeg",
        replace(inputs, caption_ass_path="captions/captions.ass"),
        load_channel_config("engineering-es").render,
        tmp_path / "out.mp4",
    )
    graph = command[command.index("-filter_complex") + 1]
    assert "ass=filename=captions/captions.ass[v]" in graph
    assert "C:" not in graph and "\\" not in graph
    assert str(inputs.project_directory.resolve() / "narration.wav") in command
    assert str(inputs.project_directory.resolve() / "assets/scene-01.png") in command


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is unavailable"
)
def test_captioned_mp4_remains_valid_with_audio(tmp_path: Path) -> None:
    project_id, store, _ = fixture_project(tmp_path)
    channel = load_channel_config("engineering-es")
    CaptionProjectUseCase(store, LocalCaptionAlignmentProvider(), channel).execute(project_id)
    artifact = RenderProjectUseCase(
        store, FFmpegRenderer(), channel.render, channel.captions
    ).execute(project_id)
    assert (artifact.width, artifact.height, artifact.frame_rate) == (1080, 1920, 30)
    assert (artifact.video_codec, artifact.audio_codec, artifact.pixel_format) == (
        "h264",
        "aac",
        "yuv420p",
    )
    assert abs(artifact.duration_seconds - 2) <= 2 / 30
