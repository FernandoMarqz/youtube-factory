"""Errors exposed by application use cases."""


class ContentPipelineError(Exception):
    """Base error for the local content pipeline."""


class UnsupportedTopicError(ContentPipelineError):
    """Raised when a deterministic provider has no fixture for a topic."""


class ProviderContractError(ContentPipelineError):
    """Raised when a provider returns invalid or inconsistent data."""


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
