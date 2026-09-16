"""Deterministic local adapters used before external integrations."""

from youtube_factory.adapters.local.artifact_store import FileSystemArtifactStore
from youtube_factory.adapters.local.caption_alignment import LocalCaptionAlignmentProvider
from youtube_factory.adapters.local.narration_generator import LocalNarrationGenerator
from youtube_factory.adapters.local.research import LocalResearchProvider
from youtube_factory.adapters.local.scene_planner import LocalScenePlanner
from youtube_factory.adapters.local.script_generator import LocalScriptGenerator
from youtube_factory.adapters.local.visual_assets import LocalPlaceholderVisualAssetProvider

__all__ = [
    "FileSystemArtifactStore",
    "LocalCaptionAlignmentProvider",
    "LocalNarrationGenerator",
    "LocalResearchProvider",
    "LocalScenePlanner",
    "LocalScriptGenerator",
    "LocalPlaceholderVisualAssetProvider",
]
