"""Typed curated music loading and deterministic, offline track selection."""

import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from youtube_factory.application.config.models import MusicSelectionConfig
from youtube_factory.application.exceptions import MusicCatalogError, MusicSelectionError
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


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(re.findall(r"\w+", value, flags=re.UNICODE))


def _matches(text: str, phrase: str) -> bool:
    normalized = _normalize(phrase.replace("_", " "))
    return bool(normalized and f" {normalized} " in f" {text} ")


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
        if script.topic_id != topic.id:
            raise MusicSelectionError("script and topic differ for music selection")
        text = _normalize(f"{topic.title} {script.full_narration}")
        profiles = [
            (name, profile, sum(_matches(text, word) for word in profile.keywords))
            for name, profile in preferences.keyword_profiles.items()
        ]
        profiles.sort(key=lambda item: (-item[2], item[0]))
        profile_name, profile, hits = profiles[0] if profiles else (None, None, 0)
        if not hits:
            profile_name, profile = None, None
        moods = set(preferences.preferred_moods)
        niches = set(preferences.preferred_niches)
        topics: set[str] = set()
        energy = preferences.preferred_energy
        category = None
        if profile is not None:
            moods.update(profile.moods)
            niches.update(profile.niches)
            topics.update(profile.suitable_topics)
            energy = profile.energy or energy
            category = profile.category
        eligible = [
            track
            for track in catalog.catalog.tracks
            if preferences.allow_attribution_required or not track.attribution_required
        ]
        if not eligible:
            raise MusicSelectionError("no eligible music tracks after attribution filtering")
        scored: list[tuple[int, MusicTrack, tuple[str, ...], tuple[str, ...]]] = []
        for track in eligible:
            matched_topics = tuple(sorted(topics.intersection(track.suitable_topics)))
            matched_moods = tuple(sorted(moods.intersection(track.moods)))
            direct_topics = tuple(item for item in track.suitable_topics if _matches(text, item))
            energy_gap = abs(ENERGY_LEVELS.index(energy) - ENERGY_LEVELS.index(track.energy))
            score = (
                (4 if matched_topics or direct_topics else 0)
                + (3 if matched_moods else 0)
                + (3 if category == track.category else 0)
                + (2 if niches.intersection(track.niches) else 0)
                + (2 if energy_gap == 0 else 1 if energy_gap == 1 else 0)
                + (1 if set(preferences.preferred_genres).intersection(track.genres) else 0)
            )
            all_topics = tuple(sorted(set(matched_topics + direct_topics)))
            scored.append((score, track, matched_moods, all_topics))
        best = max(score for score, _, _, _ in scored)
        pool = sorted((entry for entry in scored if entry[0] >= best - 2), key=lambda e: e[1].id)
        choice = int.from_bytes(sha256(str(topic.id).encode("ascii")).digest()[:8], "big")
        score, track, matched_moods, matched_topics = pool[choice % len(pool)]
        selected = SelectedMusicTrack(
            track_id=track.id,
            title=track.title,
            artist=track.artist,
            file_path=f"assets/music/{track.file_path}",
            catalog_file_path=track.file_path,
            selection=MusicSelectionDetails(
                mode="catalog",
                score=score,
                matched_moods=matched_moods,
                matched_topics=matched_topics,
                profile=profile_name,
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
