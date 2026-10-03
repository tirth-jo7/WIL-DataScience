from __future__ import annotations

import re
from typing import Protocol

from .config import MIN_RETRIEVAL_SCORE, TOP_K
from .prompts import (
    CRISIS_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_crisis_prompt,
    build_user_prompt,
)
from .safety import classify_input
from .schemas import (
    Classification,
    LLMAnswer,
    RagRequest,
    RagResponse,
    RagSource,
    ResponseBody,
    RetrievedSource,
    SafetyMetadata,
    Source,
)

_MARKDOWN_LINK_RE = re.compile(
    r"\[([^\]]+)\]\(https?://[^)\s]+\)",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)


def _sanitize_answer_text(text: str) -> str:
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)
    text = _URL_RE.sub("", text)
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class Generator(Protocol):
    async def generate(self, system_prompt: str, user_prompt: str) -> LLMAnswer:
        ...


class Retriever(Protocol):
    @property
    def using_vector_store(self) -> bool:
        ...

    def retrieve(
        self,
        query: str,
        top_k: int = TOP_K,
        topic: str | None = None,
    ) -> list[RetrievedSource]:
        ...

    def get_source(self, source_id: str) -> Source | None:
        ...


class RagService:
    def __init__(
        self,
        retriever: Retriever,
        generator: Generator,
        *,
        top_k: int = TOP_K,
        min_retrieval_score: float = MIN_RETRIEVAL_SCORE,
    ) -> None:
        self.retriever = retriever
        self.generator = generator
        self.top_k = top_k
        self.min_retrieval_score = min_retrieval_score

    async def handle(self, request: RagRequest) -> RagResponse:
        question = request.message.text.strip()
        safety = classify_input(question)

        if safety.route == "crisis":
            return await self._crisis_response(request.requestId, question)

        if safety.route == "clinical":
            return self._clinical_scope_response(request.requestId)

        if safety.route == "prompt_injection":
            return self._unsupported_response(
                request.requestId,
                (
                    "I can help with verified student support information, but I can't "
                    "follow requests to override the assistant's safety or source rules."
                ),
            )

        retrieved = self._retrieve(
            question,
            top_k=self.top_k,
            topic=None,
        )

        if not retrieved:
            return self._unsupported_response(
                request.requestId,
                (
                    "I couldn't find enough verified information in the student-support "
                    "knowledge base to answer that reliably. Try rephrasing the question "
                    "or describing the support you need."
                ),
            )

        # Vector-store rows may not expose a comparable numeric similarity score through
        # Role 3's public interface. Keep the old threshold only for the BM25 fallback.
        if (
            not self._using_vector_store()
            and retrieved[0].score < self.min_retrieval_score
        ):
            return self._unsupported_response(
                request.requestId,
                (
                    "I couldn't find enough verified information in the student-support "
                    "knowledge base to answer that reliably. Try rephrasing the question "
                    "or describing the support you need."
                ),
            )

        generated = await self._generate_grounded_answer(question, retrieved)
        if generated is None:
            return self._unsupported_response(
                request.requestId,
                (
                    "I couldn't generate a grounded answer right now. Please use the "
                    "verified university support information directly and try again shortly."
                ),
            )

        if generated.type == "crisis":
            return self._unsupported_response(
                request.requestId,
        (
            "I couldn't classify that response reliably from the "
            "verified student-support information. Please try "
            "rephrasing your question."
        ),
    )

        if generated.clinicalAdvice:
            return self._clinical_scope_response(request.requestId)

        if generated.type == "unsupported":
            return self._unsupported_response(request.requestId, generated.text)

        selected = self._validate_sources(generated, retrieved)
        if selected is None:
            return self._unsupported_response(
                request.requestId,
                (
                    "I couldn't verify the sources for that answer, so I won't present "
                    "it as supported information."
                ),
            )

        answer_text = _sanitize_answer_text(generated.text)
        if not answer_text:
            return self._unsupported_response(
                request.requestId,
                "I couldn't produce a safely formatted grounded answer from the verified sources.",
            )

        return self._navigation_response(
            request.requestId,
            answer_text,
            generated.confidence,
            selected,
        )

    def _using_vector_store(self) -> bool:
        # Existing unit tests construct RagService with BM25Retriever directly,
        # while production wraps it in HybridRetriever. Support both.
        return bool(getattr(self.retriever, "using_vector_store", False))

    def _retrieve(
        self,
        query: str,
        *,
        top_k: int,
        topic: str | None = None,
    ) -> list[RetrievedSource]:
        try:
            return self.retriever.retrieve(
                query,
                top_k=top_k,
                topic=topic,
            )
        except TypeError as exc:
            # BM25Retriever predates the Role 3 topic-filter interface. Retry
            # without topic so existing tests and the fallback keep working.
            if "topic" not in str(exc):
                raise
            return self.retriever.retrieve(query, top_k=top_k)

    async def _generate_grounded_answer(
        self,
        question: str,
        retrieved: list[RetrievedSource],
    ) -> LLMAnswer | None:
        try:
            return await self.generator.generate(
                SYSTEM_PROMPT,
                build_user_prompt(question, retrieved),
            )
        except Exception:
            return None

    def _validate_sources(
        self,
        generated: LLMAnswer,
        retrieved: list[RetrievedSource],
    ) -> list[RetrievedSource] | None:
        retrieved_by_id = {source.id: source for source in retrieved}
        requested_ids = list(dict.fromkeys(generated.source_ids))
        selected = [
            retrieved_by_id[source_id]
            for source_id in requested_ids
            if source_id in retrieved_by_id
        ]
        if len(selected) != len(requested_ids) or not selected:
            return None
        return selected

    async def _crisis_response(
        self,
        request_id: str,
        question: str,
    ) -> RagResponse:
        # Role 3's topic filter means an urgent query searches only verified crisis
        # material (e.g. RMIT, Lifeline, Beyond Blue) instead of relying on its rank
        # against the entire corpus.
        crisis_sources = self._retrieve(
            question,
            top_k=max(self.top_k, 4),
            topic="crisis",
        )

        if crisis_sources and self._using_vector_store():
            try:
                generated = await self.generator.generate(
                    CRISIS_SYSTEM_PROMPT,
                    build_crisis_prompt(question, crisis_sources),
                )
                selected = self._validate_sources(generated, crisis_sources)
                answer_text = _sanitize_answer_text(generated.text)
                if (
                    generated.type == "crisis"
                    and not generated.clinicalAdvice
                    and selected
                    and answer_text
                ):
                    return RagResponse(
                        requestId=request_id,
                        response=ResponseBody(text=answer_text),
                        classification=Classification(
                            type="crisis",
                            confidence=generated.confidence,
                        ),
                        sources=self._rag_sources(selected),
                        safety=SafetyMetadata(
                            crisisDetected=True,
                            clinicalAdvice=False,
                        ),
                    )
            except Exception:
                pass

        # Fail-safe used before the vector store is merged or if crisis generation fails.
        source = self.retriever.get_source("emergency_crisis")
        fallback_sources = (
            [RagSource(title=source.title, url=source.url)]
            if source
            else []
        )
        return RagResponse(
            requestId=request_id,
            response=ResponseBody(
                text=(
                    "Please use one of the verified urgent-support " + "or emergency services listed below."
                )
            ),
            classification=Classification(type="crisis", confidence=1.0),
            sources=fallback_sources,
            safety=SafetyMetadata(crisisDetected=True, clinicalAdvice=False),
        )

    def _clinical_scope_response(self, request_id: str) -> RagResponse:
        source = self.retriever.get_source("counselling")
        sources = (
            [RagSource(title=source.title, url=source.url)]
            if source
            else []
        )
        return RagResponse(
            requestId=request_id,
            response=ResponseBody(
                text=(
                    "I can explain verified support options, but I can't diagnose a condition, "
                    "prescribe treatment, or recommend medication. A qualified health "
                    "professional or student counselling service can discuss those concerns."
                )
            ),
            classification=Classification(type="unsupported", confidence=1.0),
            sources=sources,
            safety=SafetyMetadata(crisisDetected=False, clinicalAdvice=False),
        )

    def _unsupported_response(self, request_id: str, text: str) -> RagResponse:
        return RagResponse(
            requestId=request_id,
            response=ResponseBody(text=text),
            classification=Classification(type="unsupported", confidence=1.0),
            sources=[],
            safety=SafetyMetadata(crisisDetected=False, clinicalAdvice=False),
        )

    def _navigation_response(
        self,
        request_id: str,
        text: str,
        confidence: float,
        sources: list[RetrievedSource],
    ) -> RagResponse:
        return RagResponse(
            requestId=request_id,
            response=ResponseBody(text=text),
            classification=Classification(type="navigation", confidence=confidence),
            sources=self._rag_sources(sources),
            safety=SafetyMetadata(crisisDetected=False, clinicalAdvice=False),
        )

    @staticmethod
    def _rag_sources(sources: list[RetrievedSource]) -> list[RagSource]:
        seen: set[tuple[str, str | None]] = set()
        output: list[RagSource] = []
        for source in sources:
            key = (source.title, source.url)
            if key in seen:
                continue
            seen.add(key)
            output.append(RagSource(title=source.title, url=source.url))
        return output


