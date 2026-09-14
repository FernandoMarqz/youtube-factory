"""Research provider boundary."""

from typing import Protocol

from youtube_factory.domain.models import ResearchResult, Topic


class ResearchProvider(Protocol):
    """Produces a validated research result for a topic."""

    identifier: str

    def research(self, topic: Topic) -> ResearchResult:
        """Research the supplied topic."""
