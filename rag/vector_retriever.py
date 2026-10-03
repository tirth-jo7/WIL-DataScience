from __future__ import annotations

import hashlib
import importlib
import re
from pathlib import Path
from typing import Any, Callable

from .retrieval import BM25Retriever
from .schemas import RetrievedSource

_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_META_RE = re.compile(r"^(?:source|url)\s*:\s*(https?://\S+)", re.IGNORECASE | re.MULTILINE)
_DATE_RE = re.compile(r"^(?:date|last[_ -]?verified)\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)


class HybridRetriever:
    """
    Adapter around the project's retrieval backend.

    Preferred backend (Role 3):
        retrieval.store.retrieve(query, top_k=4, topic=None)

    Until Role 3's code is present, the adapter falls back to the existing
    BM25 retriever so the RAG service remains runnable.
    """

    def __init__(self, fallback: BM25Retriever) -> None:
        self.fallback = fallback
        self._vector_retrieve = self._load_vector_retrieve()

    @property
    def using_vector_store(self) -> bool:
        return self._vector_retrieve is not None

    @property
    def backend_name(self) -> str:
        return "vector_store" if self.using_vector_store else "bm25_fallback"

    def retrieve(
        self,
        query: str,
        top_k: int = 4,
        topic: str | None = None,
    ) -> list[RetrievedSource]:
        if self._vector_retrieve is None:
            # The BM25 fallback has no topic metadata. It is only here so this
            # branch keeps working before Role 3's vector-store PR is merged.
            return self.fallback.retrieve(query, top_k=top_k)

        rows = self._vector_retrieve(
            query,
            top_k=top_k,
            topic=topic,
        )

        return [
            self._normalise_result(row, index)
            for index, row in enumerate(rows or [])
            if isinstance(row, dict)
        ]

    def get_source(self, source_id: str):
        # Fixed fallback sources are still useful for fail-safe messages.
        return self.fallback.get_source(source_id)

    @staticmethod
    def _load_vector_retrieve() -> Callable[..., list[dict[str, Any]]] | None:
        try:
            module = importlib.import_module("retrieval.store")
            retrieve_fn = getattr(module, "retrieve", None)
            if callable(retrieve_fn):
                return retrieve_fn
        except (ImportError, ModuleNotFoundError):
            pass
        return None

    @classmethod
    def _normalise_result(
        cls,
        row: dict[str, Any],
        index: int,
    ) -> RetrievedSource:
        text = str(row.get("text") or "").strip()
        source = str(row.get("source") or "").strip()
        topic = str(row.get("topic") or "general").strip()

        url = cls._extract_url(source, text)
        title = cls._extract_title(source, text, topic)
        last_verified = cls._extract_date(text)

        stable_key = f"{source}|{topic}|{text[:240]}|{index}"
        source_id = "vector_" + hashlib.sha1(
            stable_key.encode("utf-8")
        ).hexdigest()[:12]

        return RetrievedSource(
            id=source_id,
            title=title,
            url=url,
            content=text,
            tags=[topic] if topic else [],
            last_verified=last_verified,
            score=1.0,
            raw_score=1.0,
        )

    @staticmethod
    def _extract_url(source: str, text: str) -> str | None:
        if source.startswith("http://") or source.startswith("https://"):
            return source.rstrip(".,);]")

        metadata_match = _META_RE.search(text)
        if metadata_match:
            return metadata_match.group(1).rstrip(".,);]")

        text_match = _URL_RE.search(text)
        if text_match:
            return text_match.group(0).rstrip(".,);]")

        return None

    @staticmethod
    def _extract_title(source: str, text: str, topic: str) -> str:
        heading = _TITLE_RE.search(text)
        if heading:
            return heading.group(1).strip()

        if source and not source.startswith("http"):
            return Path(source).stem.replace("_", " ").replace("-", " ").strip().title()

        if source.startswith("http"):
            return "Verified support source"

        return f"{topic.title()} support source"

    @staticmethod
    def _extract_date(text: str) -> str | None:
        match = _DATE_RE.search(text)
        return match.group(1).strip() if match else None
