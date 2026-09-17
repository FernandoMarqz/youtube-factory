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
from youtube_factory.application.config.models import MusicKeywordProfile
from youtube_factory.application.exceptions import MusicCatalogError, MusicSelectionError
from youtube_factory.application.music_text import matches_music_phrase, normalize_music_text
from youtube_factory.application.services.music import (
    ContentMusicProfileBuilder,
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


def _topic_script(
    title: str, topic_id: UUID | None = None, body: str = "Una explicación breve."
) -> tuple[Topic, Script]:
    topic = Topic(id=topic_id or uuid4(), title=title)
    script = Script(
        topic_id=topic.id,
        hook=title,
        body=body,
        ending="Ahora lo sabes.",
        full_narration=f"{title} {body} Ahora lo sabes.",
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


def test_music_keyword_matching_handles_accents_phrases_and_boundaries() -> None:
    text = normalize_music_text("¿Cómo funciona la vía férrea junto al hormigón?")
    assert matches_music_phrase(text, "como funciona")
    assert matches_music_phrase(text, "vía férrea")
    assert matches_music_phrase(text, "via ferrea")
    assert matches_music_phrase(text, "hormigon")
    assert not matches_music_phrase(normalize_music_text("La lluvia cambia"), "ia")
    assert not matches_music_phrase(normalize_music_text("Química"), "maquina")


def test_music_profile_config_rejects_duplicate_normalized_keywords_and_names() -> None:
    with pytest.raises(ValidationError, match="unique after normalization"):
        MusicKeywordProfile(keywords=("vía", "via"))
    with pytest.raises(ValidationError):
        MusicKeywordProfile(keywords=("tren",), moods=("",))
    with pytest.raises(ValidationError):
        MusicKeywordProfile(keywords=("tren",), energy="fast")  # type: ignore[arg-type]
    selection = load_channel_config("engineering-es").audio.music.selection
    payload = selection.model_dump()
    profile = {"keywords": ("tren",)}
    payload["keyword_profiles"] = {"Rail": profile, "rail": profile}
    with pytest.raises(ValidationError, match="names must be non-empty and unique"):
        type(selection).model_validate(payload)


def test_railway_infers_structural_profile_and_auditable_signals() -> None:
    topic, script = _topic_script(
        "¿Por qué las vias del tren tienen piedra debajo y no solo concreto liso?",
        body="El balasto sujeta las traviesas; el concreto liso no sustituye siempre a la vía.",
    )
    preferences = load_channel_config("engineering-es").audio.music.selection
    profile = ContentMusicProfileBuilder().build(topic, script, preferences)
    assert profile.primary_name == "structural_infrastructure"
    assert profile.matched_profiles == ("structural_infrastructure", "general_educational")
    assert {"tren", "balasto", "traviesas", "concreto"}.issubset(profile.matched_keywords)
    assert {"engineering", "infrastructure", "transportation"}.issubset(profile.topics)
    assert {"technical", "curious"}.issubset(profile.moods)
    assert profile.energy == "medium"
    catalog = load_music_catalog(Path(__file__).resolve().parents[1] / "assets/music/catalog.yaml")
    selected, _ = DeterministicCatalogMusicSelector().select(catalog, topic, script, preferences)
    assert selected.selection.profile == "structural_infrastructure"
    assert selected.selection.matched_topics
    assert "transportation" in selected.selection.inferred_topics
    assert "technical" in selected.selection.inferred_moods


def test_futuristic_machinery_general_and_default_profiles() -> None:
    preferences = load_channel_config("engineering-es").audio.music.selection
    builder = ContentMusicProfileBuilder()
    ai = builder.build(
        *_topic_script("¿Cómo aprende una inteligencia artificial?", body="Usa datos."),
        preferences,
    )
    assert ai.primary_name == "futuristic_technology"
    assert {"technology", "ai", "space"}.issubset(ai.topics)
    assert "futuristic" in ai.moods
    engine = builder.build(
        *_topic_script(
            "¿Por qué un motor a reacción produce tanto empuje?", body="El motor acelera aire."
        ),
        preferences,
    )
    assert engine.primary_name == "machinery_energy"
    assert engine.energy == "high"
    assert {"machines", "engines", "transportation"}.issubset(engine.topics)
    general = builder.build(
        *_topic_script("¿Por qué sucede esto?", body="Un detalle interesante."),
        preferences,
    )
    assert general.primary_name == "general_educational"
    default = builder.build(
        *_topic_script("Objeto peculiar", body="Detalles sin palabras clave."),
        preferences,
    )
    assert default.primary_name == "default"
    assert default.matched_profiles == ()
    assert default.energy == preferences.preferred_energy
    assert set(preferences.preferred_moods).issubset(default.moods)


def test_profile_phrase_weight_tiebreak_merge_and_primary_energy() -> None:
    preferences = load_channel_config("engineering-es").audio.music.selection
    custom = preferences.model_copy(
        update={
            "keyword_profiles": {
                "alpha": MusicKeywordProfile(
                    keywords=("inteligencia artificial",),
                    topics=("ai",),
                    moods=("futuristic",),
                    energy="medium",
                ),
                "beta": MusicKeywordProfile(
                    keywords=("artificial", "tecnologia"),
                    topics=("technology",),
                    moods=("modern",),
                    energy="high",
                ),
            }
        }
    )
    builder = ContentMusicProfileBuilder()
    profile = builder.build(
        *_topic_script("Inteligencia artificial", body="Tecnología moderna."), custom
    )
    assert profile.primary_name == "alpha"  # phrase +3 beats token +1
    assert profile.matched_profiles == ("alpha", "beta")
    assert profile.topics == ("ai", "technology")
    assert profile.energy == "medium"
    tied = custom.model_copy(
        update={
            "keyword_profiles": {
                "zeta": MusicKeywordProfile(keywords=("artificial",), energy="high"),
                "alpha": MusicKeywordProfile(keywords=("inteligencia",), energy="low"),
            }
        }
    )
    assert builder.build(*_topic_script("Inteligencia artificial"), tied).primary_name == "alpha"


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
    assert choice.selection.profile == "structural_infrastructure"
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
    isolated = baseline.model_copy(update={"keyword_profiles": {}})
    genres = isolated.model_copy(update={"preferred_genres": ("electronic",)})
    no_genres = isolated.model_copy(update={"preferred_genres": ()})
    catalog = _catalog(tmp_path / "genre", [_track("one")])
    assert (
        selector.select(catalog, topic, script, genres)[0].selection.score
        > selector.select(catalog, topic, script, no_genres)[0].selection.score
    )
    niches = isolated.model_copy(update={"preferred_niches": ("engineering",)})
    no_niches = isolated.model_copy(update={"preferred_niches": ()})
    assert (
        selector.select(catalog, topic, script, niches)[0].selection.score
        > selector.select(catalog, topic, script, no_niches)[0].selection.score
    )


def test_real_catalog_topic_profiles_and_stable_variety(tmp_path: Path) -> None:
    path = Path(__file__).resolve().parents[1] / "assets/music/catalog.yaml"
    catalog = load_music_catalog(path)
    selector = DeterministicCatalogMusicSelector()
    preferences = load_channel_config("engineering-es").audio.music.selection
    for title, profile_name in (
        ("¿Por qué los puentes tienen juntas de dilatación?", "structural_infrastructure"),
        ("¿Cómo funciona un satélite en el espacio?", "futuristic_technology"),
        ("¿Cómo funciona el motor de una megaconstrucción?", "machinery_energy"),
    ):
        topic, script = _topic_script(title)
        selected, _ = selector.select(catalog, topic, script, preferences)
        assert selected.selection.profile == profile_name
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
    selected_path = inputs.project_directory / "selected-music.json"
    original = selected_path.read_bytes()
    simplified = channel.audio.music.selection.model_copy(update={"keyword_profiles": {}})
    changed_music = channel.audio.music.model_copy(update={"selection": simplified})
    changed_audio = channel.audio.model_copy(update={"music": changed_music})
    changed_use_case = RenderProjectUseCase(
        store, renderer, channel.render, audio=changed_audio, catalog_root=tmp_path
    )
    changed_use_case.execute(project_id)
    assert selected_path.read_bytes() == original
    changed_use_case.execute(project_id, reselect_music=True)
    assert json.loads(selected_path.read_bytes())["selection"]["profile"] == "default"
    assert len(renderer.music_paths) == 3
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
