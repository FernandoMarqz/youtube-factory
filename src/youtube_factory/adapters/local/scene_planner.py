"""Fixture-like deterministic audiovisual planner for Phase 2."""

from youtube_factory.application.exceptions import UnsupportedTopicError
from youtube_factory.domain.enums import AssetType
from youtube_factory.domain.models import Scene, ScenePlan, Script


class LocalScenePlanner:
    """Fixture-like planner retained for offline development and regression tests."""

    identifier = "local-scene-planner-v1"
    provider = "local"
    model: str | None = None

    def plan(self, script: Script) -> ScenePlan:
        """Plan a 34-second audiovisual timeline without producing media."""
        if script.full_narration.startswith("¿Sabías") is False:
            raise UnsupportedTopicError("unsupported script for local scene planning")
        return ScenePlan(
            topic_id=script.topic_id,
            total_duration_seconds=34.0,
            scenes=[
                Scene(
                    sequence=1,
                    narration_segment=(
                        "¿Sabías que una tapa redonda no puede caerse por su propio agujero?"
                    ),
                    start_seconds=0.0,
                    end_seconds=3.5,
                    duration_seconds=3.5,
                    visual_description=(
                        "Vista cenital de una tapa circular sobre una boca de alcantarilla."
                    ),
                    visual_intent="Abrir con una pregunta visualmente sorprendente.",
                    asset_type=AssetType.DIAGRAM,
                    on_screen_text="¿Por qué son redondas?",
                    transition_suggestion="Corte rápido al detalle geométrico.",
                ),
                Scene(
                    sequence=2,
                    narration_segment=(
                        "Esa es la razón más práctica: tenga la orientación que tenga,"
                    ),
                    start_seconds=3.5,
                    end_seconds=7.5,
                    duration_seconds=4.0,
                    visual_description="Diagrama de la tapa girando sobre la abertura circular.",
                    visual_intent="Introducir que el giro no altera el encaje.",
                    asset_type=AssetType.ANIMATION,
                    transition_suggestion="Fundido breve al esquema de diámetro.",
                ),
                Scene(
                    sequence=3,
                    narration_segment="su diámetro siempre es mayor que la abertura.",
                    start_seconds=7.5,
                    end_seconds=12.0,
                    duration_seconds=4.5,
                    visual_description=(
                        "Corte transversal con una tapa circular detenida sobre su abertura."
                    ),
                    visual_intent="Explicar visualmente por qué la tapa no puede caer dentro.",
                    asset_type=AssetType.DIAGRAM,
                    on_screen_text="El diámetro la detiene",
                    transition_suggestion="Barrido hacia el encaje desde arriba.",
                ),
                Scene(
                    sequence=4,
                    narration_segment="Además, la redonda no necesita alinearse para encajar",
                    start_seconds=12.0,
                    end_seconds=16.0,
                    duration_seconds=4.0,
                    visual_description=(
                        "Comparativa superior: varias rotaciones de la misma tapa circular encajan."
                    ),
                    visual_intent=("Mostrar que no hace falta buscar una orientación concreta."),
                    asset_type=AssetType.ANIMATION,
                    transition_suggestion="Corte a una situación de mantenimiento.",
                ),
                Scene(
                    sequence=5,
                    narration_segment="y se puede rodar hasta el lugar de trabajo.",
                    start_seconds=16.0,
                    end_seconds=20.0,
                    duration_seconds=4.0,
                    visual_description=(
                        "Operario empujando una tapa circular de canto por una acera."
                    ),
                    visual_intent=(
                        "Conectar la geometría con una ventaja práctica de manipulación."
                    ),
                    asset_type=AssetType.IMAGE,
                    transition_suggestion="Fundido a un esquema estructural.",
                ),
                Scene(
                    sequence=6,
                    narration_segment="Su forma también puede ayudar a distribuir las cargas,",
                    start_seconds=20.0,
                    end_seconds=24.5,
                    duration_seconds=4.5,
                    visual_description=(
                        "Diagrama simplificado de flechas de carga repartidas alrededor del aro."
                    ),
                    visual_intent=(
                        "Ilustrar una posible ventaja estructural sin afirmarla como universal."
                    ),
                    asset_type=AssetType.DIAGRAM,
                    on_screen_text="Cargas según el diseño",
                    transition_suggestion="Zoom hacia la advertencia final.",
                ),
                Scene(
                    sequence=7,
                    narration_segment=(
                        "según cómo esté construida la boca. No es una regla universal,"
                    ),
                    start_seconds=24.5,
                    end_seconds=29.0,
                    duration_seconds=4.5,
                    visual_description=(
                        "Dos bocas de alcantarilla estilizadas con rótulos de diseños distintos."
                    ),
                    visual_intent="Matizar que las decisiones reales dependen de la estructura.",
                    asset_type=AssetType.DIAGRAM,
                    on_screen_text="Depende del diseño",
                    transition_suggestion="Corte limpio al resumen geométrico.",
                ),
                Scene(
                    sequence=8,
                    narration_segment=(
                        "pero para una abertura circular, la geometría hace que la tapa redonda "
                        "sea una solución especialmente segura y práctica."
                    ),
                    start_seconds=29.0,
                    end_seconds=34.0,
                    duration_seconds=5.0,
                    visual_description=(
                        "Tapa circular encajando vista desde arriba con tres iconos: segura, sin "
                        "alineación y rodable."
                    ),
                    visual_intent="Cerrar con el beneficio geométrico y un resumen memorable.",
                    asset_type=AssetType.ANIMATION,
                    on_screen_text="Segura y práctica",
                ),
            ],
        )
