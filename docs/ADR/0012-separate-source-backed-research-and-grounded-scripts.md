# ADR 0012 — Separate Source-Backed Research From Grounded Script Generation

## Status

Accepted

## Context

Arbitrary-topic content requires external factual retrieval and editorial script generation. A
single combined LLM call would make it difficult to inspect sources, determine which claims grounded
the script, replace providers independently, or improve research quality without changing writing.

## Decision

Keep `ResearchProvider` and `ScriptGenerator` as separate provider-neutral ports and persist their
outputs independently. OpenAI research uses the Responses API web-search tool and a provider-private
Structured Output DTO. Every persisted external URL must match source evidence returned by the tool.
Zero usable sources stops the pipeline.

OpenAI script generation receives only the validated `Topic` and `ResearchResult`; it has no search
tool. Its prompt forbids new factual claims, and its structured result references persisted key facts
by index. Application code constructs `full_narration`, copies those exact facts into `Script.claims`,
and estimates spoken duration deterministically. Semantic entailment or a second-model fact checker
is intentionally deferred.

Local research and script adapters remain deterministic reference fixtures and the safe channel
defaults. CLI overrides select OpenAI explicitly; there is no implicit fallback.

## Consequences

Positive:

- `research.json` is independently reviewable and source-backed;
- `script.json` can be traced to exact persisted research facts;
- research and editorial providers can evolve independently;
- arbitrary topics can traverse the creative pipeline without changing domain contracts;
- offline regression behavior remains stable.

Negative:

- a full AI run makes separate paid research and script requests;
- source evidence validates URL provenance, not the truth of every generated sentence;
- prompt grounding plus exact claim references do not replace future semantic fact checking.
