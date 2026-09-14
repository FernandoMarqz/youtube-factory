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
