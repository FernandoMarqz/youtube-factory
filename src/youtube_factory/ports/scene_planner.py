"""Scene-planning provider boundary."""

from typing import Protocol

from youtube_factory.domain.models import ScenePlan, Script


class ScenePlanner(Protocol):
    """Transforms a validated script into a timed audiovisual plan."""

    identifier: str

    def plan(self, script: Script) -> ScenePlan:
        """Return a continuous audiovisual timeline for the script."""
