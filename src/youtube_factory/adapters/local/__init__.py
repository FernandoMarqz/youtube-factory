"""Deterministic local adapters used before external integrations."""

from youtube_factory.adapters.local.artifact_store import FileSystemArtifactStore
from youtube_factory.adapters.local.narration_generator import LocalNarrationGenerator
from youtube_factory.adapters.local.research import LocalResearchProvider
from youtube_factory.adapters.local.scene_planner import LocalScenePlanner
from youtube_factory.adapters.local.script_generator import LocalScriptGenerator

__all__ = [
    "FileSystemArtifactStore",
    "LocalNarrationGenerator",
    "LocalResearchProvider",
    "LocalScenePlanner",
    "LocalScriptGenerator",
]
