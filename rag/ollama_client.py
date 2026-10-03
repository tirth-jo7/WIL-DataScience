from __future__ import annotations

from copy import deepcopy

import httpx

from .config import (
    OLLAMA_HOST,
    OLLAMA_MODEL,
    REQUEST_TIMEOUT_SECONDS,
)
from .prompts import CRISIS_SYSTEM_PROMPT
from .schemas import LLMAnswer


def _response_schema(system_prompt: str) -> dict:
    """
    Build a different structured-output schema depending on
    whether this is normal RAG generation or crisis generation.
    """

    schema = deepcopy(
        LLMAnswer.model_json_schema()
    )

    type_schema = schema["properties"]["type"]

    is_crisis_prompt = (
        system_prompt.strip()
        == CRISIS_SYSTEM_PROMPT.strip()
    )

    if is_crisis_prompt:
        # The application has already deterministically routed
        # this request to the crisis pathway.
        type_schema["enum"] = ["crisis"]

    else:
        # Normal requests must never be escalated to crisis
        # based on the LLM's own classification.
        type_schema["enum"] = [
            "navigation",
            "unsupported",
        ]

    return schema


class OllamaClient:
    def __init__(
        self,
        *,
        host: str = OLLAMA_HOST,
        model: str = OLLAMA_MODEL,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMAnswer:

        is_crisis_prompt = (
            system_prompt.strip()
            == CRISIS_SYSTEM_PROMPT.strip()
        )

        payload = {
            "model": self.model,

            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],

            "format": _response_schema(
                system_prompt
            ),

            "stream": False,

            "options": {
                "temperature": 0,
            },
        }

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds
        ) as client:

            response = await client.post(
                f"{self.host}/api/chat",
                json=payload,
            )

            response.raise_for_status()

            body = response.json()

        content = (
            body
            .get("message", {})
            .get("content")
        )

        if (
            not isinstance(content, str)
            or not content.strip()
        ):
            raise ValueError(
                "Ollama returned an empty chat response"
            )

        answer = LLMAnswer.model_validate_json(
            content
        )

        # Fail closed if the model somehow violates the schema.
        if (
            not is_crisis_prompt
            and answer.type == "crisis"
        ):
            raise ValueError(
                "Normal RAG generation returned "
                "an invalid crisis classification"
            )

        if (
            is_crisis_prompt
            and answer.type != "crisis"
        ):
            raise ValueError(
                "Crisis generation returned "
                "a non-crisis classification"
            )

        return answer