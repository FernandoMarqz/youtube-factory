# ADR 0017 - Curated Deterministic Music Selection

## Status

Accepted

## Context

Phase 7 mixes a project-local music file but does not choose one. A manually curated library and
`assets/music/catalog.yaml` already exist. Selection must be offline, auditable and stable for an
existing project even when the catalog changes.

## Decision

Load the existing YAML safely into typed, immutable catalog tracks. Resolve every catalog path
relative to its library root and reject missing, empty or escaping paths. Treat license metadata
as user-provided data, never inferred truth. For catalog mode, normalize Spanish topic/script text
only for matching channel-configured keyword profiles. Score eligible tracks by suitable topic
(4), mood (3), profile category (3), niche (2), energy (2 exact or 1 adjacent), and preferred
genre (1). Exclude attribution-required tracks unless explicitly allowed. Sort the pool within
two points of the best score by track ID, then choose using a SHA-256 hash of the stable topic ID.

Copy the chosen file into the project and persist `selected-music.json`, including original
catalog metadata and source path. Normal `render-project` reuses that project-local copy without
reopening the catalog. `--reselect-music` explicitly reruns selection and overwrites the choice.
The FFmpeg mixer still receives only a resolved project-relative file path and existing mix
settings. Disabled and manual modes bypass the catalog entirely.

## Consequences

- Existing projects keep their soundtrack when catalog order or scoring changes.
- Project directories include an audio copy for reproducible offline rerenders.
- Missing persisted audio fails; it never silently selects a replacement.
- Acquisition, licensing verification and automated downloading remain outside runtime.
