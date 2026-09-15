# ADR 0009 — Separate Channel Editorial Configuration From Secrets And Artifacts

## Status

Accepted

## Context

The platform will eventually support several channels with different language, narration and visual
preferences. Placing those editorial choices in environment variables would make them machine-local,
hard to review, and difficult to reproduce. Persisting entire configurations in generated artifacts
would duplicate source configuration and risk retaining inappropriate data.

## Decision

Use three explicit configuration boundaries:

```text
.env                         secrets and machine-local infrastructure
config/channels/*.yaml       version-controlled channel/editorial preferences
data/projects/<project-id>/  generated runtime artifacts
```

Channel YAML is loaded with `yaml.safe_load` into immutable Pydantic models at the CLI composition
root. The domain and provider adapters do not read YAML or environment variables. An explicit CLI
provider override takes precedence over the selected channel for one invocation only.

## Consequences

Positive:

- editorial settings are reviewable and reproducible;
- secrets remain out of version-controlled configuration and artifacts;
- future visual and publishing preferences have a typed home without implementing those capabilities;
- adapters receive explicit configuration through constructors.

Negative:

- every execution must select a valid channel configuration;
- configuration changes require schema and fixture maintenance.
