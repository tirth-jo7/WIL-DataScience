from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from .schemas import RetrievedSource, Source

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")

# Common function words should not make an unrelated query look relevant.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by",
    "can", "could", "do", "for", "from", "get", "have", "help", "i", "if",
    "in", "is", "it", "me", "my", "of", "on", "or", "someone", "that",
    "the", "their", "there", "this", "to", "want", "what", "where", "who",
    "with", "you", "your",
}


def tokenize(text: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS]


class BM25Retriever:
    """Small dependency-free BM25 baseline inspired by Walert's BM25 RAG setup."""

    def __init__(
        self,
        documents: list[Source],
        *,
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        if not documents:
            raise ValueError("Knowledge base must contain at least one source")

        self.documents = documents
        self.k1 = k1
        self.b = b

        self._tokens = [self._document_tokens(doc) for doc in documents]
        self._lengths = [len(tokens) for tokens in self._tokens]
        self._avg_length = sum(self._lengths) / len(self._lengths)
        self._term_frequencies = [Counter(tokens) for tokens in self._tokens]

        doc_frequency: Counter[str] = Counter()
        for tokens in self._tokens:
            doc_frequency.update(set(tokens))
        self._doc_frequency = doc_frequency

    @classmethod
    def from_json(cls, path: str | Path) -> "BM25Retriever":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        docs = [Source.model_validate(item) for item in payload]
        return cls(docs)

    def get_source(self, source_id: str) -> Source | None:
        return next((doc for doc in self.documents if doc.id == source_id), None)

    def retrieve(self, query: str, top_k: int = 3) -> list[RetrievedSource]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scored: list[tuple[float, Source]] = []
        n_docs = len(self.documents)

        for index, document in enumerate(self.documents):
            frequencies = self._term_frequencies[index]
            doc_len = self._lengths[index]
            raw_score = 0.0

            for term in query_tokens:
                tf = frequencies.get(term, 0)
                if tf == 0:
                    continue

                df = self._doc_frequency.get(term, 0)
                idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * doc_len / self._avg_length
                )
                raw_score += idf * (tf * (self.k1 + 1)) / denominator

            if raw_score > 0:
                scored.append((raw_score, document))

        scored.sort(key=lambda item: item[0], reverse=True)

        results: list[RetrievedSource] = []
        for raw_score, document in scored[:top_k]:
            normalized = raw_score / (raw_score + 1.0)
            results.append(
                RetrievedSource(
                    **document.model_dump(),
                    raw_score=raw_score,
                    score=normalized,
                )
            )
        return results

    @staticmethod
    def _document_tokens(document: Source) -> list[str]:
        # Tags are deliberately repeated to make service-intent terms stronger than
        # incidental words in the descriptive paragraph.
        tag_text = " ".join(document.tags)
        combined = f"{document.title} {tag_text} {tag_text} {document.content}"
        return tokenize(combined)
