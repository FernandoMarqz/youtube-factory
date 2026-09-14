"""Enumerations shared by the provider-independent domain."""

from enum import StrEnum


class HookType(StrEnum):
    """Narrative pattern used to open a short."""

    QUESTION = "question"
    SURPRISING_FACT = "surprising_fact"
    PROBLEM = "problem"
    CONTRAST = "contrast"


class AssetType(StrEnum):
    """Media form used by a scene."""

    IMAGE = "image"
    VIDEO = "video"
    DIAGRAM = "diagram"
    ANIMATION = "animation"


class AssetSourceType(StrEnum):
    """Origin of a visual asset."""

    GENERATED = "generated"
    SOURCED = "sourced"
    LOCAL = "local"


class RenderStatus(StrEnum):
    """State of a rendering attempt."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProjectStatus(StrEnum):
    """Lifecycle states needed before human-reviewed publication."""

    DRAFT = "draft"
    GENERATING = "generating"
    RENDERED = "rendered"
    REVIEW_PENDING = "review_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
