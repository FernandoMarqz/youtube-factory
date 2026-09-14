"""Script generation boundary."""

from typing import Protocol

from youtube_factory.domain.models import ResearchResult, Script, Topic


class ScriptGenerator(Protocol):
    """Produces a validated Short script from researched material."""

    identifier: str

    def generate(self, topic: Topic, research: ResearchResult) -> Script:
        """Generate a script for the supplied researched topic."""
