"""Fixture-like deterministic script generator for Phase 1."""

from youtube_factory.adapters.local.research import SUPPORTED_TOPIC
from youtube_factory.application.exceptions import UnsupportedTopicError
from youtube_factory.domain.enums import HookType
from youtube_factory.domain.models import ResearchResult, Script, Topic


class LocalScriptGenerator:
    """Produces one stable, short-form Spanish script for the reference topic."""

    identifier = "local-script-v1"
    provider = "local"
    model: str | None = None

    def generate(self, topic: Topic, research: ResearchResult) -> Script:
        """Generate the deterministic script using the supplied research contract."""
        if topic.title != SUPPORTED_TOPIC:
            raise UnsupportedTopicError(f"unsupported topic: {topic.title}")
        if research.topic_id != topic.id:
            raise UnsupportedTopicError("research does not belong to the requested topic")
        hook = "¿Sabías que una tapa redonda no puede caerse por su propio agujero?"
        body = (
            "Esa es la razón más práctica: tenga la orientación que tenga, su diámetro siempre "
            "es mayor que la abertura. Además, la redonda no necesita alinearse para encajar y "
            "se puede rodar hasta el lugar de trabajo. Su forma también puede ayudar a distribuir "
            "las cargas, según cómo esté construida la boca."
        )
        ending = (
            "No es una regla universal, pero para una abertura circular, la geometría hace que "
            "la tapa redonda sea una solución especialmente segura y práctica."
        )
        return Script(
            topic_id=topic.id,
            hook=hook,
            body=body,
            ending=ending,
            full_narration=f"{hook} {body} {ending}",
            hook_type=HookType.QUESTION,
            estimated_duration_seconds=34.0,
            claims=research.key_facts[:4],
        )
