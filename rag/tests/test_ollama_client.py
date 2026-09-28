from __future__ import annotations

import json

import pytest

from rag.ollama_client import OllamaClient


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "message": {
                "content": json.dumps(
                    {
                        "text": "RMIT counselling may be suitable.",
                        "type": "navigation",
                        "confidence": 0.9,
                        "source_ids": ["counselling"],
                        "clinicalAdvice": False,
                    }
                )
            }
        }


class FakeAsyncClient:
    last_payload: dict | None = None
    last_url: str | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, json: dict):
        FakeAsyncClient.last_url = url
        FakeAsyncClient.last_payload = json
        return FakeResponse()


@pytest.mark.asyncio
async def test_ollama_chat_uses_structured_output(monkeypatch) -> None:
    monkeypatch.setattr("rag.ollama_client.httpx.AsyncClient", FakeAsyncClient)
    client = OllamaClient(host="http://localhost:11434", model="test-model")

    answer = await client.generate("system", "user")

    assert answer.source_ids == ["counselling"]
    assert FakeAsyncClient.last_url == "http://localhost:11434/api/chat"
    assert FakeAsyncClient.last_payload["model"] == "test-model"
    assert FakeAsyncClient.last_payload["stream"] is False
    assert FakeAsyncClient.last_payload["options"]["temperature"] == 0
    assert FakeAsyncClient.last_payload["format"]["type"] == "object"
