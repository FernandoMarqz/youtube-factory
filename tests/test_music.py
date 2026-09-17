"""Offline catalog, selector and persisted-music workflow coverage."""

import json
import shutil
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import yaml
from pydantic import ValidationError
from test_audio import _tone_wav
from test_rendering import fixture_project

from youtube_factory.adapters.ffmpeg import FFmpegRenderer
from youtube_factory.adapters.local import FileSystemArtifactStore
from youtube_factory.application.config import AudioConfig, RenderConfig, load_channel_config
from youtube_factory.application.exceptions import MusicCatalogError, MusicSelectionError
from youtube_factory.application.services.music import (
    DeterministicCatalogMusicSelector,
    LoadedMusicCatalog,
    load_music_catalog,
)
from youtube_factory.application.use_cases import RenderProjectUseCase
from youtube_factory.domain.enums import HookType
from youtube_factory.domain.models import ContentManifest, RenderArtifact, Script, Topic
from youtube_factory.ports import RenderInputs


def _track(
    track_id: str,
    *,
    category: str = "educational",
    energy: str = "medium",
    moods: tuple[str, ...] = ("curious",),
    topics: tuple[str, ...] = ("structures",),
    attribution: bool = False,
) -> dict[str, object]:
    return {
        "id": track_id,
        "title": track_id,
        "artist": "Test Artist",
        "file_path": f"{category}/{track_id}.wav",
        "category": category,
        "energy": energy,
        "moods": list(moods),
        "genres": ["electronic"],
        "niches": ["engineering"],
        "suitable_topics": list(topics),
        "source": "test-catalog",
        "source_url": "https://example.org/catalog",
        "license_type": "test-license",
        "attribution_required": attribution,
        "attribution_text": "Credit Test Artist" if attribution else None,
    }


def _catalog(tmp_path: Path, tracks: list[dict[str, object]]) -> LoadedMusicCatalog:
    root = tmp_path / "assets/music"
    root.mkdir(parents=True, exist_ok=True)
    for track in tracks:
        path = root / str(track["file_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture audio")
    (root / "catalog.yaml").write_text(
        yaml.safe_dump({"version": 1, "tracks": tracks}), encoding="utf-8"
    )
    return load_music_catalog(root / "catalog.yaml")


def _topic_script(title: str, topic_id: UUID | None = None) -> tuple[Topic, Script]:
    topic = Topic(id=topic_id or uuid4(), title=title)
    script = Script(
        topic_id=topic.id,
        hook=title,
        body="Una explicación breve.",
        ending="Ahora lo sabes.",
        full_narration=f"{title} Una explicación breve. Ahora lo sabes.",
        hook_type=HookType.QUESTION,
        estimated_duration_seconds=30,
        claims=["A test claim"],
    )
    return topic, script


def test_existing_curated_catalog_loads_without_rewriting_it() -> None:
    path = Path(__file__).resolve().parents[1] / "assets/music/catalog.yaml"
    before = path.read_bytes()
    loaded = load_music_catalog(path)
    assert len(loaded.catalog.tracks) == 10
    assert {track.category for track in loaded.catalog.tracks} == {
        "futuristic",
        "tech",
        "educational",
        "energetic",
        "exploration",
    }
    assert loaded.catalog.tracks[0].energy == "medium"
    assert loaded.catalog.tracks[0].license_type == "youtube-audio-library"
    assert "space" in loaded.catalog.tracks[0].suitable_topics
    assert loaded.catalog.tracks[0].moods == ("futuristic", "curious", "mysterious", "modern")
    assert path.read_bytes() == before


def test_catalog_rejects_duplicate_ids_missing_files_and_bad_metadata(tmp_path: Path) -> None:
    first = _track("one")
    loaded = _catalog(tmp_path, [first])
    path = loaded.root / "catalog.yaml"
    for tracks in (
        [first, first],
        [first | {"attribution_required": True, "attribution_text": None}],
        [first | {"energy": "unknown"}],
        [first | {"file_path": "../escape.wav"}],
    ):
        path.write_text(yaml.safe_dump({"version": 1, "tracks": tracks}), encoding="utf-8")
        with pytest.raises(MusicCatalogError):
            load_music_catalog(path)
    path.write_text(yaml.safe_dump({"version": 1, "tracks": [first]}), encoding="utf-8")
    (loaded.root / str(first["file_path"])).unlink()
    with pytest.raises(MusicCatalogError, match="missing or empty"):
        load_music_catalog(path)
    path.write_text("tracks: [", encoding="utf-8")
    with pytest.raises(MusicCatalogError, match="invalid music catalog"):
        load_music_catalog(path)


def test_channel_music_modes_are_immutable_and_validated() -> None:
    channel = load_channel_config("engineering-es")
    assert channel.audio.music.enabled and channel.audio.music.mode == "catalog"
    assert channel.audio.music.file_path is None
    with pytest.raises(ValidationError):
        channel.audio.music.mode = "manual"
    for change in (
        {"mode": "manual", "file_path": None},
        {"mode": "catalog", "file_path": "track.mp3"},
        {"catalog_path": "../catalog.yaml"},
        {"selection": {"preferred_energy": "invalid"}},
    ):
        payload = channel.audio.music.model_dump() | change
        with pytest.raises(ValidationError):
            type(channel.audio.music).model_validate(payload)


def test_selector_uses_multiple_signals_and_licensing_filter(tmp_path: Path) -> None:
    catalog = _catalog(
        tmp_path,
        [
            _track("bridge", energy="low-medium", moods=("technical",), topics=("structures",)),
            _track(
                "energetic",
                category="energetic",
                energy="high",
                moods=("energetic",),
                topics=("engines",),
            ),
        ],
    )
    topic, script = _topic_script("¿Por qué los puentes tienen juntas de dilatación?")
    choice, _ = DeterministicCatalogMusicSelector().select(
        catalog, topic, script, load_channel_config("engineering-es").audio.music.selection
    )
    assert choice.track_id == "bridge"
    assert choice.selection.profile == "structural"
    assert choice.selection.matched_topics == ("structures",)
    assert choice.license.source == "test-catalog"
    restricted = _catalog(tmp_path, [_track("credit", attribution=True)])
    with pytest.raises(MusicSelectionError, match="no eligible"):
        DeterministicCatalogMusicSelector().select(
            restricted, topic, script, load_channel_config("engineering-es").audio.music.selection
        )
    allowed = load_channel_config("engineering-es").audio.music.selection.model_copy(
        update={"allow_attribution_required": True}
    )
    selected, _ = DeterministicCatalogMusicSelector().select(restricted, topic, script, allowed)
    assert selected.license.attribution_required
    assert selected.license.attribution_text == "Credit Test Artist"


def test_each_scoring_signal_contributes_independently(tmp_path: Path) -> None:
    topic, script = _topic_script("¿Por qué los puentes tienen juntas de dilatación?")
    selector = DeterministicCatalogMusicSelector()
    baseline = load_channel_config("engineering-es").audio.music.selection
    cases = (
        ("topic", {"topics": ("structures",)}, {"topics": ("unrelated",)}),
        ("mood", {"moods": ("technical",)}, {"moods": ("unrelated",)}),
        ("category", {"category": "educational"}, {"category": "exploration"}),
        ("energy", {"energy": "low-medium"}, {"energy": "high"}),
    )
    for name, good, bad in cases:
        preferred = _catalog(tmp_path / name / "good", [_track("good", **good)])
        other = _catalog(tmp_path / name / "bad", [_track("bad", **bad)])
        good_score = selector.select(preferred, topic, script, baseline)[0].selection.score
        bad_score = selector.select(other, topic, script, baseline)[0].selection.score
        assert good_score > bad_score, name
    genres = baseline.model_copy(update={"preferred_genres": ("electronic",)})
    no_genres = baseline.model_copy(update={"preferred_genres": ()})
    catalog = _catalog(tmp_path / "genre", [_track("one")])
    assert (
        selector.select(catalog, topic, script, genres)[0].selection.score
        > selector.select(catalog, topic, script, no_genres)[0].selection.score
    )
    niches = baseline.model_copy(update={"preferred_niches": ("engineering",)})
    no_niches = baseline.model_copy(update={"preferred_niches": ()})
    assert (
        selector.select(catalog, topic, script, niches)[0].selection.score
        > selector.select(catalog, topic, script, no_niches)[0].selection.score
    )


def test_real_catalog_topic_profiles_and_stable_variety(tmp_path: Path) -> None:
    path = Path(__file__).resolve().parents[1] / "assets/music/catalog.yaml"
    catalog = load_music_catalog(path)
    selector = DeterministicCatalogMusicSelector()
    preferences = load_channel_config("engineering-es").audio.music.selection
    for title, category in (
        ("¿Por qué los puentes tienen juntas de dilatación?", "educational"),
        ("¿Cómo funciona un satélite en el espacio?", "futuristic"),
        ("¿Cómo funciona el motor de una megaconstrucción?", "energetic"),
    ):
        topic, script = _topic_script(title)
        selected, _ = selector.select(catalog, topic, script, preferences)
        assert selected.catalog_file_path.startswith(f"{category}/")
        assert selector.select(catalog, topic, script, preferences)[0] == selected
    varied = _catalog(tmp_path, [_track("a"), _track("b"), _track("c")])
    choices = {
        selector.select(varied, *_topic_script("Bridge", UUID(int=index + 1)), preferences)[
            0
        ].track_id
        for index in range(12)
    }
    assert len(choices) > 1


class RecordingRenderer:
    provider = "ffmpeg"
    identifier = "recording-renderer"

    def __init__(self) -> None:
        self.music_paths: list[str | None] = []

    def render(self, inputs: RenderInputs, config: RenderConfig) -> RenderArtifact:
        self.music_paths.append(inputs.audio.music.file_path)
        output = inputs.project_directory / "render/short.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fixture mp4")
        return RenderArtifact(
            provider="ffmpeg",
            file_path="render/short.mp4",
            duration_seconds=2,
            width=config.width,
            height=config.height,
            frame_rate=config.fps,
            video_codec="h264",
            audio_codec="aac",
            pixel_format="yuv420p",
            file_size_bytes=11,
        )


def _persist_context(store: FileSystemArtifactStore, project_id: str, title: str) -> None:
    topic, script = _topic_script(title, UUID(project_id))
    directory = store._project_directory(project_id)
    (directory / "topic.json").write_text(topic.model_dump_json(), encoding="utf-8")
    (directory / "script.json").write_text(script.model_dump_json(), encoding="utf-8")


def test_catalog_choice_persists_and_rerender_reuses_it(tmp_path: Path) -> None:
    project_id, store, inputs = fixture_project(tmp_path / "projects")
    _persist_context(store, project_id, "¿Por qué los puentes tienen juntas de dilatación?")
    catalog = _catalog(tmp_path, [_track("one"), _track("two")])
    channel = load_channel_config("engineering-es")
    renderer = RecordingRenderer()
    use_case = RenderProjectUseCase(
        store, renderer, channel.render, audio=channel.audio, catalog_root=tmp_path
    )
    use_case.execute(project_id)
    path = inputs.project_directory / "selected-music.json"
    selected_before = path.read_bytes()
    selection = json.loads(selected_before)
    assert (inputs.project_directory / selection["file_path"]).is_file()
    assert renderer.music_paths[-1] == selection["file_path"]
    manifest = ContentManifest.model_validate_json(
        (inputs.project_directory / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest.music_selector is not None
    assert manifest.music_selector.track_id == selection["track_id"]
    assert "selected-music.json" in manifest.artifacts
    assert selection["file_path"] in manifest.artifacts
    (catalog.root / "catalog.yaml").write_text("invalid: [", encoding="utf-8")
    use_case.execute(project_id)
    assert path.read_bytes() == selected_before
    assert renderer.music_paths[-1] == selection["file_path"]
    (inputs.project_directory / selection["file_path"]).unlink()
    with pytest.raises(MusicSelectionError, match="missing"):
        use_case.execute(project_id)


def test_reselection_manual_and_disabled_modes(tmp_path: Path) -> None:
    project_id, store, inputs = fixture_project(tmp_path / "projects")
    _persist_context(store, project_id, "Puente")
    _catalog(tmp_path, [_track("one"), _track("two")])
    channel = load_channel_config("engineering-es")
    renderer = RecordingRenderer()
    use_case = RenderProjectUseCase(
        store, renderer, channel.render, audio=channel.audio, catalog_root=tmp_path
    )
    use_case.execute(project_id)
    use_case.execute(project_id, reselect_music=True)
    assert len(renderer.music_paths) == 2
    manual = AudioConfig.model_validate(
        channel.audio.model_dump()
        | {
            "music": channel.audio.music.model_dump()
            | {"mode": "manual", "file_path": "assets/music/manual.wav"}
        }
    )
    (inputs.project_directory / "assets/music/manual.wav").write_bytes(b"manual")
    RenderProjectUseCase(store, renderer, channel.render, audio=manual).execute(project_id)
    assert renderer.music_paths[-1] == "assets/music/manual.wav"
    disabled = AudioConfig.model_validate(
        channel.audio.model_dump()
        | {"music": channel.audio.music.model_dump() | {"enabled": False}}
    )
    RenderProjectUseCase(store, renderer, channel.render, audio=disabled).execute(project_id)
    assert renderer.music_paths[-1] is None
    with pytest.raises(MusicSelectionError, match="requires enabled catalog"):
        RenderProjectUseCase(store, renderer, channel.render, audio=disabled).execute(
            project_id, reselect_music=True
        )


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is unavailable"
)
def test_catalog_selection_feeds_real_phase7_mixer(tmp_path: Path) -> None:
    project_id, store, inputs = fixture_project(tmp_path / "projects")
    _persist_context(store, project_id, "¿Por qué los puentes tienen juntas de dilatación?")
    catalog = _catalog(tmp_path, [_track("synthetic")])
    _tone_wav(
        catalog.root / "educational/synthetic.wav",
        frequency=440,
        seconds=0.5,
        amplitude=0.2,
        channels=2,
        sample_rate=22050,
    )
    channel = load_channel_config("engineering-es")
    artifact = RenderProjectUseCase(
        store, FFmpegRenderer(), channel.render, audio=channel.audio, catalog_root=tmp_path
    ).execute(project_id)
    assert (artifact.width, artifact.height, artifact.frame_rate) == (1080, 1920, 30)
    assert (artifact.video_codec, artifact.audio_codec, artifact.pixel_format) == (
        "h264",
        "aac",
        "yuv420p",
    )
    assert abs(artifact.duration_seconds - 2) <= 2 / 30
    assert artifact.audio_mix is not None and artifact.audio_mix.music_enabled
    assert artifact.audio_mix.ducking_enabled
    assert (inputs.project_directory / "selected-music.json").is_file()
    assert (inputs.project_directory / "audio-mix.json").is_file()
