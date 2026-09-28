from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
TOP_K = int(os.getenv("RAG_TOP_K", "3"))
MIN_RETRIEVAL_SCORE = float(os.getenv("RAG_MIN_RETRIEVAL_SCORE", "0.18"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
KNOWLEDGE_BASE_PATH = Path(
    os.getenv("RAG_KB_PATH", str(BASE_DIR / "data" / "services.json"))
)
