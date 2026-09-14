"""Tests for Phase 1 content contracts."""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import HttpUrl, ValidationError

from youtube_factory.domain.enums import HookType
from youtube_factory.domain.models import ResearchResult, Script, Source


def test_research_result_accepts_valid_contract() -> None:
    result = ResearchResult(
        topic_id=uuid4(),
        summary="Resumen verificado.",
        key_facts=["Hecho verificable."],
        sources=[
            Source(
                title="Fuente",
                url=HttpUrl("https://example.com/source"),
                publisher="Editorial",
                retrieved_at=datetime(2026, 1, 1),
            )
        ],
    )

    assert result.key_facts == ["Hecho verificable."]


def test_script_accepts_valid_contract() -> None:
    script = Script(
        topic_id=uuid4(),
        hook="Un gancho claro.",
        body="Una explicación concisa.",
        ending="Un cierre útil.",
        full_narration="Un gancho claro. Una explicación concisa. Un cierre útil.",
        hook_type=HookType.QUESTION,
        estimated_duration_seconds=30,
        claims=["Una afirmación respaldada."],
    )

    assert script.estimated_duration_seconds == 30


def test_research_result_rejects_an_empty_fact_list() -> None:
    with pytest.raises(ValidationError):
        ResearchResult(
            topic_id=uuid4(),
            summary="Resumen.",
            key_facts=[],
            sources=[],
        )
