from __future__ import annotations

from fastapi import FastAPI

from .config import KNOWLEDGE_BASE_PATH
from .ollama_client import OllamaClient
from .retrieval import BM25Retriever
from .schemas import RagRequest, RagResponse
from .service import RagService
from .vector_retriever import HybridRetriever

app = FastAPI(title="Student Support RAG")

# BM25 remains a temporary fallback and a useful baseline for evaluation.
# When Role 3's retrieval/store.py exists, HybridRetriever automatically uses
# retrieve(query, top_k=..., topic=...) from that vector-store implementation.
bm25_fallback = BM25Retriever.from_json(KNOWLEDGE_BASE_PATH)
retriever = HybridRetriever(fallback=bm25_fallback)
service = RagService(retriever=retriever, generator=OllamaClient())


@app.get("/health")
def health() -> dict[str, str]:
    # Keep the original API contract used by the existing tests/client.
    return {"status": "ok"}


@app.get("/health/retrieval")
def retrieval_health() -> dict[str, str]:
    return {
        "status": "ok",
        "retrievalBackend": retriever.backend_name,
    }


@app.post("/query", response_model=RagResponse)
async def query(request: RagRequest) -> RagResponse:
    # Do not log full student messages: support/wellbeing messages can be sensitive.
    return await service.handle(request)
