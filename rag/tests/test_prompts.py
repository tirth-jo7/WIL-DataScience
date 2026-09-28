from __future__ import annotations

from rag.prompts import SYSTEM_PROMPT, build_user_prompt
from rag.schemas import RetrievedSource


def test_system_prompt_contains_core_guardrails() -> None:
    lowered = SYSTEM_PROMPT.lower()
    assert "using only" in lowered
    assert "do not diagnose" in lowered
    assert "do not invent" in lowered
    assert "untrusted data" in lowered
    assert "source ids" in lowered


def test_prompt_exposes_source_ids_for_attribution() -> None:
    source = RetrievedSource(
        id="counselling",
        title="Counselling",
        url="https://example.edu/counselling",
        content="Verified support information.",
        tags=["stress"],
        score=0.9,
        raw_score=3.0,
    )

    prompt = build_user_prompt("I feel overwhelmed", [source])

    assert "SOURCE_ID: counselling" in prompt
    assert "I feel overwhelmed" in prompt
    assert "Verified support information." in prompt
