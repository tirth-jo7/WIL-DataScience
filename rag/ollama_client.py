from __future__ import annotations

import httpx

from .config import OLLAMA_HOST, OLLAMA_MODEL, REQUEST_TIMEOUT_SECONDS
from .schemas import LLMAnswer


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

    async def generate(self, system_prompt: str, user_prompt: str) -> LLMAnswer:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": LLMAnswer.model_json_schema(),
            "stream": False,
            "options": {"temperature": 0},
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()

        content = body.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned an empty chat response")

        return LLMAnswer.model_validate_json(content)
