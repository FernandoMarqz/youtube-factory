# ADR 0010 — Separate Visual Intent, Provider Prompts And Generated Assets

## Status

Accepted

## Context

A scene's visual description expresses creative meaning, but image providers need more detailed
instructions about channel style, composition, orientation, caption-safe space and exclusions.
Treating the scene description as the final provider prompt would couple scene planning to current
provider behavior and make prompt changes overwrite the original storyboard intent.

## Decision

Preserve three explicit, provider-neutral concepts:

- `TimedScenePlan` is the media-aligned semantic storyboard.
- `VisualPromptPlan` contains generation-ready instructions built independently of providers.
- `VisualAssetManifest` maps generated binary assets back to scene sequences and exact prompt hashes.

`VisualPromptBuilder` is an application boundary. `VisualAssetProvider` receives only a validated
`VisualPrompt` and returns image bytes plus provider-neutral metadata. Binary persistence remains the
responsibility of `ProjectArtifactStore`.

## Consequences

Positive:

- prompt strategy can evolve without changing scene planning or provider adapters;
- local and paid providers share the same validated input and output contracts;
- stored prompts and SHA-256 hashes make generation inputs inspectable;
- future renderers need no OpenAI knowledge.

Negative:

- the project stores two additional JSON artifacts;
- prompt and asset sequence consistency must be validated during orchestration.
