"""Offline caption contracts, reconciliation, planning, storage and media tests."""

import re
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
from youtube_factory.application.exceptions import CaptionAlignmentError, CaptionPlanningError
from youtube_factory.application.services.canonical_alignment import reconcile_words
from youtube_factory.application.services.captions import CaptionPlanner, build_ass
from youtube_factory.application.use_cases import CaptionProjectUseCase, RenderProjectUseCase
from youtube_factory.domain.models import (
    AlignedWord,
    CaptionCue,
    CaptionPlan,
    Narration,
    WordAlignment,
)


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
    assert captions.emphasis.enabled and captions.emphasis.mode == "word"
    assert captions.emphasis.active_color == "#FFD54A"
    with pytest.raises(ValidationError):
        captions.emphasis.active_color = "#000000"
    with pytest.raises(ValidationError):
        captions.enabled = False
    for change in (
        {"grouping": captions.grouping.model_dump() | {"max_words_per_cue": 0}},
        {"grouping": captions.grouping.model_dump() | {"max_cue_duration_seconds": 0.1}},
        {"style": captions.style.model_dump() | {"max_lines": 3}},
        {"alignment": {"provider": "unknown"}},
        {"alignment": {"provider": "openai"}},
        {"emphasis": {"mode": "karaoke"}},
        {"emphasis": {"active_color": "yellow"}},
        {"emphasis": {"inactive_color": "#12345"}},
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
    assert plan.cues[0].word_start_index == 0
    assert plan.cues[-1].word_end_index == len(first.words)
    assert all(
        left.word_end_index == right.word_start_index
        for left, right in zip(plan.cues, plan.cues[1:], strict=False)
    )
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


def _dynamic_fixture() -> tuple[WordAlignment, CaptionPlan]:
    sample = narration("¿Por qué el puente, cambia?")
    words = [
        AlignedWord(text=text, start_seconds=start, end_seconds=end)
        for text, start, end in (
            ("¿Por", 0.015, 0.205),
            ("qué", 0.205, 0.4),
            ("el", 0.5, 0.7),
            ("puente,", 0.7, 1.1),
            ("cambia?", 1.3, 1.7),
        )
    ]
    alignment = WordAlignment(
        topic_id=sample.topic_id, provider="fixture", duration_seconds=2, words=words
    )
    plan = CaptionPlan(
        topic_id=sample.topic_id,
        language="es-ES",
        cues=[
            CaptionCue(
                sequence=1,
                text=sample.narration_text,
                start_seconds=0.015,
                end_seconds=1.7,
                word_start_index=0,
                word_end_index=5,
            )
        ],
    )
    return alignment, plan


def _dialogues(ass: str) -> list[tuple[str, str, str]]:
    return [
        (fields[1], fields[2], fields[9])
        for line in ass.splitlines()
        if line.startswith("Dialogue:")
        for fields in [line.split(",", 9)]
    ]


def test_dynamic_ass_uses_absolute_word_intervals_and_stable_layout() -> None:
    alignment, plan = _dynamic_fixture()
    captions = load_channel_config("engineering-es").captions
    ass = build_ass(
        plan,
        captions.style,
        1080,
        1920,
        18,
        alignment=alignment,
        emphasis=captions.emphasis,
    )
    events = _dialogues(ass)
    assert events[0][0] == "0:00:00.02"
    assert events[-1][1] == "0:00:01.70"
    assert all(left[1] == right[0] for left, right in zip(events, events[1:], strict=False))
    assert "&H4AD5FF&" in ass  # RGB #FFD54A converted to ASS BGR.
    assert "&H00FFFFFF&" in ass
    assert any(
        start == "0:00:00.40" and end == "0:00:00.50" and "{\\1c" not in text
        for start, end, text in events
    )
    assert any("{\\1c&H4AD5FF&}puente,{\\r}" in text for _, _, text in events)
    assert all(text.count("\\N") == 1 for _, _, text in events)
    assert all(text.count("\\N") <= 1 for _, _, text in events)
    plain = {re.sub(r"\{\\[^}]+\}", "", text) for _, _, text in events}
    assert plain == {"¿Por qué el\\Npuente, cambia?"}


def test_dynamic_ass_supports_legacy_cues_and_rejects_bad_mapping() -> None:
    alignment, plan = _dynamic_fixture()
    captions = load_channel_config("engineering-es").captions
    legacy = plan.model_copy(
        update={
            "cues": [
                plan.cues[0].model_copy(update={"word_start_index": None, "word_end_index": None})
            ]
        }
    )
    assert _dialogues(
        build_ass(
            legacy,
            captions.style,
            1080,
            1920,
            18,
            alignment=alignment,
            emphasis=captions.emphasis,
        )
    )
    wrong = plan.model_copy(
        update={"cues": [plan.cues[0].model_copy(update={"text": "¿Por qué el otro cambia?"})]}
    )
    with pytest.raises(CaptionPlanningError, match="does not match canonical"):
        build_ass(
            wrong, captions.style, 1080, 1920, 18, alignment=alignment, emphasis=captions.emphasis
        )
    with pytest.raises(CaptionPlanningError, match="requires persisted"):
        build_ass(plan, captions.style, 1080, 1920, 18, emphasis=captions.emphasis)


def test_static_ass_when_emphasis_is_disabled() -> None:
    _, plan = _dynamic_fixture()
    captions = load_channel_config("engineering-es").captions
    disabled = captions.emphasis.model_copy(update={"enabled": False})
    ass = build_ass(plan, captions.style, 1080, 1920, 18, emphasis=disabled)
    assert len(_dialogues(ass)) == 1
    assert "{\\1c" not in ass
    none_mode = captions.emphasis.model_copy(update={"mode": "none"})
    assert len(_dialogues(build_ass(plan, captions.style, 1080, 1920, 18, emphasis=none_mode))) == 1


def test_dynamic_ass_short_word_and_silence_use_independent_rounding() -> None:
    sample = narration("A B")
    alignment = WordAlignment(
        topic_id=sample.topic_id,
        provider="fixture",
        duration_seconds=2,
        words=[
            AlignedWord(text="A", start_seconds=0.005, end_seconds=0.015),
            AlignedWord(text="B", start_seconds=1.505, end_seconds=1.995),
        ],
    )
    plan = CaptionPlan(
        topic_id=sample.topic_id,
        language="es-ES",
        cues=[
            CaptionCue(
                sequence=1,
                text="A B",
                start_seconds=0.005,
                end_seconds=1.995,
                word_start_index=0,
                word_end_index=2,
            )
        ],
    )
    captions = load_channel_config("engineering-es").captions
    events = _dialogues(
        build_ass(
            plan,
            captions.style,
            1080,
            1920,
            24,
            alignment=alignment,
            emphasis=captions.emphasis,
        )
    )
    assert events[0][0] == "0:00:00.00"
    assert events[-1][1] == "0:00:02.00"
    assert any(
        start in {"0:00:00.01", "0:00:00.02"}
        and end in {"0:00:01.50", "0:00:01.51"}
        and "{\\1c" not in text
        for start, end, text in events
    )
    assert all(left[1] == right[0] for left, right in zip(events, events[1:], strict=False))


def test_dynamic_ass_keeps_base_text_before_first_and_after_last_word() -> None:
    alignment, plan = _dynamic_fixture()
    cue = plan.cues[0].model_copy(update={"start_seconds": 0.0, "end_seconds": 1.9})
    extended = plan.model_copy(update={"cues": [cue]})
    captions = load_channel_config("engineering-es").captions
    events = _dialogues(
        build_ass(
            extended,
            captions.style,
            1080,
            1920,
            18,
            alignment=alignment,
            emphasis=captions.emphasis,
        )
    )
    assert events[0][0] == "0:00:00.00"
    assert "{\\1c" not in events[0][2]
    assert events[-1][1] == "0:00:01.90"
    assert "{\\1c" not in events[-1][2]


def test_dynamic_ass_one_word_cue_and_word_outside_interval() -> None:
    sample = narration("¡Puente!")
    alignment = WordAlignment(
        topic_id=sample.topic_id,
        provider="fixture",
        duration_seconds=2,
        words=[AlignedWord(text="¡Puente!", start_seconds=0.2, end_seconds=0.6)],
    )
    cue = CaptionCue(
        sequence=1,
        text="¡Puente!",
        start_seconds=0.2,
        end_seconds=0.6,
        word_start_index=0,
        word_end_index=1,
    )
    plan = CaptionPlan(topic_id=sample.topic_id, language="es-ES", cues=[cue])
    captions = load_channel_config("engineering-es").captions
    events = _dialogues(
        build_ass(
            plan,
            captions.style,
            1080,
            1920,
            24,
            alignment=alignment,
            emphasis=captions.emphasis,
        )
    )
    assert events == [("0:00:00.20", "0:00:00.60", "{\\1c&H4AD5FF&}¡Puente!{\\r}")]
    shortened = plan.model_copy(update={"cues": [cue.model_copy(update={"end_seconds": 0.5})]})
    with pytest.raises(CaptionPlanningError, match="outside its interval"):
        build_ass(
            shortened,
            captions.style,
            1080,
            1920,
            24,
            alignment=alignment,
            emphasis=captions.emphasis,
        )


def test_caption_index_contracts_reject_partial_or_discontinuous_mapping() -> None:
    alignment, plan = _dynamic_fixture()
    cue = plan.cues[0]
    with pytest.raises(ValidationError, match="both be present"):
        CaptionCue.model_validate(cue.model_dump() | {"word_end_index": None})
    with pytest.raises(ValidationError, match="exceed start"):
        CaptionCue.model_validate(cue.model_dump() | {"word_start_index": 1, "word_end_index": 1})
    first = cue.model_copy(update={"text": "¿Por qué", "end_seconds": 0.4, "word_end_index": 2})
    second = cue.model_copy(
        update={
            "sequence": 2,
            "text": "el puente, cambia?",
            "start_seconds": 0.5,
            "word_start_index": 3,
        }
    )
    with pytest.raises(ValidationError, match="contiguous"):
        CaptionPlan(topic_id=alignment.topic_id, language="es-ES", cues=[first, second])


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
    plan_before = (directory / "captions.json").read_bytes()
    assert "{\\1c&H4AD5FF&}" in original_ass
    new_style = channel.captions.style.model_copy(update={"font_size": 72})
    new_emphasis = channel.captions.emphasis.model_copy(update={"active_color": "#33CC77"})
    new_captions = channel.captions.model_copy(
        update={"style": new_style, "emphasis": new_emphasis}
    )
    RenderProjectUseCase(store, renderer, channel.render, new_captions).execute(project_id)
    changed_ass = (directory / "captions/captions.ass").read_text("utf-8")
    assert changed_ass != original_ass
    assert "{\\1c&H77CC33&}" in changed_ass
    assert (directory / "word-alignment.json").read_bytes() == alignment_before
    assert (directory / "captions.json").read_bytes() == plan_before


def test_render_project_requires_alignment_only_for_dynamic_emphasis(tmp_path: Path) -> None:
    project_id, store, inputs = fixture_project(tmp_path)
    channel = load_channel_config("engineering-es")
    CaptionProjectUseCase(store, LocalCaptionAlignmentProvider(), channel).execute(project_id)
    (inputs.project_directory / "word-alignment.json").unlink()

    class NoOpRenderer:
        identifier = "fixture"
        provider = "ffmpeg"

        def render(self, value: object, config: object) -> None:
            pytest.fail("renderer should not be called before caption validation")

    with pytest.raises(Exception, match="word-alignment.json; run caption-project"):
        RenderProjectUseCase(store, NoOpRenderer(), channel.render, channel.captions).execute(
            project_id
        )


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
