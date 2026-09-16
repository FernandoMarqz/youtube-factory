"""Errors exposed by application use cases."""


class ContentPipelineError(Exception):
    """Base error for the local content pipeline."""


class UnsupportedTopicError(ContentPipelineError):
    """Raised when a deterministic provider has no fixture for a topic."""


class ProviderContractError(ContentPipelineError):
    """Raised when a provider returns invalid or inconsistent data."""


class ProviderConfigurationError(ContentPipelineError):
    """Raised when a selected external provider lacks required configuration."""


class ResearchError(ContentPipelineError):
    """Raised when source-backed research cannot be completed."""


class ResearchValidationError(ResearchError):
    """Raised when external research is empty, ungrounded or structurally invalid."""


class ScriptGenerationError(ContentPipelineError):
    """Raised when a script provider cannot generate a Short script."""


class ScriptValidationError(ScriptGenerationError):
    """Raised when a generated script violates editorial or contract constraints."""


class ArtifactPersistenceError(ContentPipelineError):
    """Raised when project artifacts cannot be persisted."""


class IncompletePipelineError(ContentPipelineError):
    """Raised when a required pipeline stage did not produce its artifact."""


class NarrationGenerationError(ContentPipelineError):
    """Raised when narration generation cannot produce a valid audio artifact."""


class InvalidAudioArtifactError(ContentPipelineError):
    """Raised when generated audio is unreadable or contradicts its metadata."""


class TimingReconciliationError(ContentPipelineError):
    """Raised when an estimated scene plan cannot be aligned with narration timing."""


class ScenePlannerConfigurationError(ContentPipelineError):
    """Raised when the selected scene planner lacks required configuration."""


class ScenePlanningError(ContentPipelineError):
    """Raised when a scene provider cannot produce a plan."""


class ScenePlanValidationError(ScenePlanningError):
    """Raised when provider output violates semantic scene-planning invariants."""


class ChannelConfigurationError(ContentPipelineError):
    """Raised when a channel configuration cannot be loaded or validated."""


class ChannelNotFoundError(ChannelConfigurationError):
    """Raised when the requested channel configuration file does not exist."""


class VisualConfigurationError(ContentPipelineError):
    """Raised when a selected visual provider is not configured safely."""


class VisualPromptGenerationError(ContentPipelineError):
    """Raised when timed scenes cannot become valid visual prompts."""


class VisualAssetGenerationError(ContentPipelineError):
    """Raised when a visual provider cannot generate an image."""


class VisualAssetValidationError(ContentPipelineError):
    """Raised when generated image bytes are empty, malformed or unsupported."""


class RenderError(ContentPipelineError):
    """Raised when a prepared project cannot be rendered."""


class RendererUnavailableError(RenderError):
    """Raised when the selected media tools are missing."""


class RenderValidationError(RenderError):
    """Raised when render inputs or output media fail validation."""


class CaptionConfigurationError(ContentPipelineError):
    """Raised when caption provider settings are incomplete."""


class CaptionAlignmentError(ContentPipelineError):
    """Raised when acoustic word timing cannot be reconciled with narration."""


class CaptionPlanningError(ContentPipelineError):
    """Raised when aligned words cannot form readable caption cues."""


class CaptionArtifactError(ContentPipelineError):
    """Raised when caption artifacts are missing or invalid."""
