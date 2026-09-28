from __future__ import annotations

from pydantic import BaseModel, Field

from rag.ollama_client import OllamaClient


class FaithfulnessJudgement(BaseModel):
    faithful: bool
    score: float = Field(ge=0.0, le=1.0)
    unsupported_claims: list[str] = Field(default_factory=list)


_JUDGE_SYSTEM = """
You are evaluating grounding for a university wellbeing navigation assistant.
Compare the ANSWER only against the supplied VERIFIED SOURCES.
A response is faithful only when every factual claim about services, eligibility,
contact details, availability, or university processes is supported by those sources.
Do not reward plausibility or outside knowledge. Return JSON only.
""".strip()


async def judge_faithfulness(
    answer: str,
    source_text: str,
    *,
    host: str,
    model: str,
) -> FaithfulnessJudgement:
    # Use a separate direct call schema rather than the navigation answer schema.
    import httpx

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _JUDGE_SYSTEM},
            {
                "role": "user",
                "content": f"ANSWER:\n{answer}\n\nVERIFIED SOURCES:\n{source_text}",
            },
        ],
        "format": FaithfulnessJudgement.model_json_schema(),
        "stream": False,
        "options": {"temperature": 0},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(f"{host.rstrip('/')}/api/chat", json=payload)
        response.raise_for_status()
        content = response.json()["message"]["content"]
    return FaithfulnessJudgement.model_validate_json(content)
