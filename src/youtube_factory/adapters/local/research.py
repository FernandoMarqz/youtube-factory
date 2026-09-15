"""Fixture-like deterministic research provider for Phase 1."""

from datetime import datetime

from pydantic import HttpUrl

from youtube_factory.application.exceptions import UnsupportedTopicError
from youtube_factory.domain.models import ResearchResult, Source, Topic

SUPPORTED_TOPIC = "¿Por qué las tapas de alcantarilla son redondas?"
_RETRIEVED_AT = datetime(2026, 1, 1)


class LocalResearchProvider:
    """Returns curated local research only for the reference topic."""

    identifier = "local-research-v1"
    provider = "local"
    model: str | None = None

    def research(self, topic: Topic) -> ResearchResult:
        """Return the stable Phase 1 research fixture."""
        if topic.title != SUPPORTED_TOPIC:
            raise UnsupportedTopicError(f"unsupported topic: {topic.title}")
        return ResearchResult(
            topic_id=topic.id,
            summary=(
                "Las tapas circulares se usan con frecuencia porque una tapa circular no puede "
                "caer por una abertura circular de menor diámetro. También simplifican el manejo "
                "y pueden repartir cargas de forma favorable según el diseño de la estructura."
            ),
            key_facts=[
                (
                    "Una tapa circular no puede atravesar su propia abertura circular al mantener "
                    "el mismo diámetro."
                ),
                (
                    "Una tapa circular no requiere alineación rotacional para encajar en una "
                    "abertura circular."
                ),
                (
                    "Una tapa circular puede rodarse sobre el borde, lo que puede facilitar su "
                    "traslado."
                ),
                (
                    "La geometría circular puede contribuir a repartir esfuerzos de forma "
                    "uniforme, según la estructura y las cargas."
                ),
            ],
            sources=[
                Source(
                    title="Manual de diseño de estructuras de acceso",
                    url=HttpUrl("https://example.com/manual-estructuras-acceso"),
                    publisher="Referencia local de Phase 1",
                    retrieved_at=_RETRIEVED_AT,
                    notes="Fuente de fixture: no se realiza ninguna consulta de red en esta fase.",
                )
            ],
            uncertainties=[
                (
                    "No todas las tapas son circulares; la elección depende también de normas, "
                    "cargas y diseño local."
                ),
            ],
        )
