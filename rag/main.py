from __future__ import annotations

from fastapi import FastAPI

from .config import KNOWLEDGE_BASE_PATH
from .ollama_client import OllamaClient
from .retrieval import BM25Retriever
from .schemas import RagRequest, RagResponse
from .service import RagService


app = FastAPI(title="Student Wellbeing RAG")

retriever = BM25Retriever.from_json(KNOWLEDGE_BASE_PATH)
service = RagService(retriever=retriever, generator=OllamaClient())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query", response_model=RagResponse)
async def query(request: RagRequest) -> RagResponse:
    # Deliberately avoid logging request.message.text because wellbeing messages may
    # contain sensitive information. requestId is sufficient for operational tracing.
    return await service.handle(request)
