"""Typed curated music loading and deterministic, offline track selection."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from youtube_factory.application.config.models import MusicKeywordProfile, MusicSelectionConfig
from youtube_factory.application.exceptions import MusicCatalogError, MusicSelectionError
from youtube_factory.application.music_text import matches_music_phrase, normalize_music_text
from youtube_factory.domain.models import (
    MusicLicense,
    MusicSelectionDetails,
    Script,
    SelectedMusicTrack,
    Topic,
)

Energy = Literal["low", "low-medium", "medium", "medium-high", "high"]
ENERGY_LEVELS = ("low", "low-medium", "medium", "medium-high", "high")
SELECTOR_IDENTIFIER = "deterministic-catalog-music-selector-v1"


class MusicTrack(BaseModel):
    """One user-curated catalog row; values are never inferred or rewritten."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    artist: Annotated[str, Field(min_length=1)]
    file_path: Annotated[str, Field(min_length=1)]
    category: Annotated[str, Field(min_length=1)]
    energy: Energy
    moods: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)
    genres: tuple[Annotated[str, Field(min_length=1)], ...] = ()
    niches: tuple[Annotated[str, Field(min_length=1)], ...] = ()
    suitable_topics: tuple[Annotated[str, Field(min_length=1)], ...] = ()
    source: Annotated[str, Field(min_length=1)]
    source_url: Annotated[str, Field(min_length=1)]
    license_type: Annotated[str, Field(min_length=1)]
    attribution_required: bool
    attribution_text: str | None = None

    @model_validator(mode="after")
    def valid_source(self) -> "MusicTrack":
        path = PurePosixPath(self.file_path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in self.file_path
            or ":" in self.file_path
            or path.as_posix() != self.file_path
        ):
            raise ValueError("music catalog file_path must be normalized and relative")
        if self.attribution_required and not self.attribution_text:
            raise ValueError("attribution text is required when attribution is required")
        return self


class MusicCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    tracks: tuple[MusicTrack, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> "MusicCatalog":
        ids = [track.id for track in self.tracks]
        if len(ids) != len(set(ids)):
            raise ValueError("music catalog track IDs must be unique")
        return self


@dataclass(frozen=True, slots=True)
class LoadedMusicCatalog:
    catalog: MusicCatalog
    root: Path

    def path_for(self, track: MusicTrack) -> Path:
        path = (self.root / track.file_path).resolve()
        if not path.is_relative_to(self.root) or not path.is_file() or path.stat().st_size == 0:
            raise MusicCatalogError(f"missing or empty catalog music file: {track.file_path}")
        return path


class MusicSelector(Protocol):
    def select(
        self,
        catalog: LoadedMusicCatalog,
        topic: Topic,
        script: Script,
        preferences: MusicSelectionConfig,
    ) -> tuple[SelectedMusicTrack, Path]: ...


def load_music_catalog(path: Path) -> LoadedMusicCatalog:
    """Safely parse the existing catalog and validate all referenced local paths."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        catalog = MusicCatalog.model_validate(raw)
        loaded = LoadedMusicCatalog(catalog, path.resolve().parent)
        for track in catalog.tracks:
            loaded.path_for(track)
        return loaded
    except (OSError, yaml.YAMLError, ValidationError, ValueError) as error:
        raise MusicCatalogError(f"invalid music catalog {path}: {error}") from error


@dataclass(frozen=True, slots=True)
class ContentMusicProfile:
    primary_name: str
    matched_profiles: tuple[str, ...]
    matched_keywords: tuple[str, ...]
    topics: tuple[str, ...]
    moods: tuple[str, ...]
    niches: tuple[str, ...]
    genres: tuple[str, ...]
    energy: Energy
    category: str | None
    normalized_text: str


def _ordered_unique(*groups: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for group in groups for item in group))


class ContentMusicProfileBuilder:
    """Infer channel-specific intent from canonical topic and script components."""

    def build(
        self, topic: Topic, script: Script, preferences: MusicSelectionConfig
    ) -> ContentMusicProfile:
        if script.topic_id != topic.id:
            raise MusicSelectionError("script and topic differ for music selection")
        text = normalize_music_text(
            " ".join((topic.title, script.hook, script.body, script.ending))
        )
        matches: list[tuple[str, MusicKeywordProfile, int, tuple[str, ...]]] = []
        for name, profile in preferences.keyword_profiles.items():
            keywords = tuple(word for word in profile.keywords if matches_music_phrase(text, word))
            if keywords:
                score = sum(
                    3 if len(normalize_music_text(word).split()) > 1 else 1 for word in keywords
                )
                matches.append((name, profile, score, keywords))
        specific = sorted(
            (entry for entry in matches if not entry[1].fallback),
            key=lambda entry: (-entry[2], entry[0]),
        )
        general = sorted(
            (entry for entry in matches if entry[1].fallback),
            key=lambda entry: (-entry[2], entry[0]),
        )
        # A lone incidental secondary token should not dilute a much stronger profile.
        relevant_specific = (
            [specific[0]]
            + [entry for entry in specific[1:] if entry[2] >= 2 or entry[2] >= specific[0][2] - 1]
            if specific
            else []
        )
        ordered = (*relevant_specific, *general)
        primary = ordered[0] if ordered else None
        return ContentMusicProfile(
            primary_name=primary[0] if primary else "default",
            matched_profiles=tuple(entry[0] for entry in ordered),
            matched_keywords=_ordered_unique(*(entry[3] for entry in ordered)),
            topics=_ordered_unique(
                *(entry[1].topics + entry[1].suitable_topics for entry in ordered)
            ),
            moods=_ordered_unique(
                *(entry[1].moods for entry in ordered), preferences.preferred_moods
            ),
            niches=_ordered_unique(
                *(entry[1].niches for entry in ordered), preferences.preferred_niches
            ),
            genres=_ordered_unique(
                *(entry[1].genres for entry in ordered), preferences.preferred_genres
            ),
            energy=(
                primary[1].energy if primary and primary[1].energy else preferences.preferred_energy
            ),
            category=primary[1].category if primary else None,
            normalized_text=text,
        )


@dataclass(frozen=True, slots=True)
class TrackMusicScore:
    score: int
    track: MusicTrack
    matched_moods: tuple[str, ...]
    matched_topics: tuple[str, ...]


class MusicCatalogScorer:
    """Preserve the Phase 7B catalog weights independently of semantic inference."""

    def score(self, track: MusicTrack, profile: ContentMusicProfile) -> TrackMusicScore:
        matched_topics = tuple(sorted(set(profile.topics).intersection(track.suitable_topics)))
        matched_moods = tuple(sorted(set(profile.moods).intersection(track.moods)))
        direct_topics = tuple(
            item
            for item in track.suitable_topics
            if matches_music_phrase(profile.normalized_text, item)
        )
        energy_gap = abs(ENERGY_LEVELS.index(profile.energy) - ENERGY_LEVELS.index(track.energy))
        score = (
            (4 if matched_topics or direct_topics else 0)
            + (3 if matched_moods else 0)
            + (3 if profile.category == track.category else 0)
            + (2 if set(profile.niches).intersection(track.niches) else 0)
            + (2 if energy_gap == 0 else 1 if energy_gap == 1 else 0)
            + (1 if set(profile.genres).intersection(track.genres) else 0)
        )
        return TrackMusicScore(
            score,
            track,
            matched_moods,
            tuple(sorted(set(matched_topics + direct_topics))),
        )


class DeterministicCatalogMusicSelector:
    """Score several catalog signals, then hash a stable topic ID within the top pool."""

    identifier = SELECTOR_IDENTIFIER

    def select(
        self,
        catalog: LoadedMusicCatalog,
        topic: Topic,
        script: Script,
        preferences: MusicSelectionConfig,
    ) -> tuple[SelectedMusicTrack, Path]:
        profile = ContentMusicProfileBuilder().build(topic, script, preferences)
        eligible = [
            track
            for track in catalog.catalog.tracks
            if preferences.allow_attribution_required or not track.attribution_required
        ]
        if not eligible:
            raise MusicSelectionError("no eligible music tracks after attribution filtering")
        scorer = MusicCatalogScorer()
        scored = [scorer.score(track, profile) for track in eligible]
        best = max(entry.score for entry in scored)
        pool = sorted(
            (entry for entry in scored if entry.score >= best - 2),
            key=lambda entry: entry.track.id,
        )
        choice = int.from_bytes(sha256(str(topic.id).encode("ascii")).digest()[:8], "big")
        chosen = pool[choice % len(pool)]
        track = chosen.track
        selected = SelectedMusicTrack(
            track_id=track.id,
            title=track.title,
            artist=track.artist,
            file_path=f"assets/music/{track.file_path}",
            catalog_file_path=track.file_path,
            selection=MusicSelectionDetails(
                mode="catalog",
                score=chosen.score,
                matched_moods=chosen.matched_moods,
                matched_topics=chosen.matched_topics,
                profile=profile.primary_name,
                matched_profiles=profile.matched_profiles,
                matched_keywords=profile.matched_keywords,
                inferred_topics=profile.topics,
                inferred_moods=profile.moods,
                inferred_niches=profile.niches,
                inferred_genres=profile.genres,
                inferred_energy=profile.energy,
            ),
            license=MusicLicense(
                source=track.source,
                source_url=track.source_url,
                license_type=track.license_type,
                attribution_required=track.attribution_required,
                attribution_text=track.attribution_text,
            ),
        )
        return selected, catalog.path_for(track)
