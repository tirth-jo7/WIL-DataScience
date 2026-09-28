from __future__ import annotations

import re
from typing import Protocol

from .config import MIN_RETRIEVAL_SCORE, TOP_K
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .retrieval import BM25Retriever
from .safety import classify_input
from .schemas import (
    Classification,
    LLMAnswer,
    RagRequest,
    RagResponse,
    RagSource,
    ResponseBody,
    SafetyMetadata,
    Source,
)

_URL_RE = re.compile(r"https?://", re.IGNORECASE)


class Generator(Protocol):
    async def generate(self, system_prompt: str, user_prompt: str) -> LLMAnswer: ...


class RagService:
    def __init__(
        self,
        retriever: BM25Retriever,
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
            return self._crisis_response(request.requestId)

        if safety.route == "clinical":
            return self._clinical_scope_response(request.requestId)

        if safety.route == "prompt_injection":
            return self._unsupported_response(
                request.requestId,
                "I can help with finding verified student wellbeing support services, but I can't follow requests to override the assistant's safety or source rules.",
            )

        retrieved = self.retriever.retrieve(question, top_k=self.top_k)
        if not retrieved or retrieved[0].score < self.min_retrieval_score:
            return self._unsupported_response(
                request.requestId,
                "I couldn't find enough verified information in the wellbeing knowledge base to answer that safely. Try describing the kind of support you are looking for.",
            )

        user_prompt = build_user_prompt(question, retrieved)

        try:
            generated = await self.generator.generate(SYSTEM_PROMPT, user_prompt)
        except Exception:
            return self._unsupported_response(
                request.requestId,
                "I couldn't generate a grounded answer right now. Please use the verified support links provided by the university directly.",
            )

        # If the LLM notices urgency that the deterministic pre-check missed, route to
        # the fixed crisis response rather than letting the model improvise contact details.
        if generated.type == "crisis":
            return self._crisis_response(request.requestId)

        if generated.clinicalAdvice:
            return self._clinical_scope_response(request.requestId)

        if generated.type == "unsupported":
            return self._unsupported_response(request.requestId, generated.text)

        retrieved_by_id = {source.id: source for source in retrieved}
        allowed_ids = list(dict.fromkeys(generated.source_ids))
        selected = [retrieved_by_id[sid] for sid in allowed_ids if sid in retrieved_by_id]

        # Fail closed on fabricated citations or unattributed navigation answers.
        if len(selected) != len(allowed_ids) or not selected:
            return self._unsupported_response(
                request.requestId,
                "I couldn't verify the sources for that answer, so I won't present it as supported information.",
            )

        # URLs belong in the structured source list only, where they come from the KB.
        if _URL_RE.search(generated.text):
            return self._unsupported_response(
                request.requestId,
                "I couldn't verify the source formatting for that answer, so I won't present it as supported information.",
            )

        return RagResponse(
            requestId=request.requestId,
            response=ResponseBody(text=generated.text),
            classification=Classification(
                type="navigation",
                confidence=generated.confidence,
            ),
            sources=[RagSource(title=source.title, url=source.url) for source in selected],
            safety=SafetyMetadata(crisisDetected=False, clinicalAdvice=False),
        )

    def _crisis_response(self, request_id: str) -> RagResponse:
        source = self._required_source("emergency_crisis")
        text = (
            "For urgent mental health support, use RMIT's 24/7 urgent support line: "
            "call 1300 305 737 or text 0488 884 162. If there is immediate danger in Australia, call 000."
        )
        return RagResponse(
            requestId=request_id,
            response=ResponseBody(text=text),
            classification=Classification(type="crisis", confidence=1.0),
            sources=[RagSource(title=source.title, url=source.url)],
            safety=SafetyMetadata(crisisDetected=True, clinicalAdvice=False),
        )

    def _clinical_scope_response(self, request_id: str) -> RagResponse:
        source = self.retriever.get_source("counselling")
        sources = [RagSource(title=source.title, url=source.url)] if source else []
        return RagResponse(
            requestId=request_id,
            response=ResponseBody(
                text=(
                    "I can help you find support services, but I can't diagnose a condition, prescribe treatment, or recommend medication. "
                    "A qualified health professional or RMIT counselling service can discuss your concerns with you."
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

    def _required_source(self, source_id: str) -> Source:
        source = self.retriever.get_source(source_id)
        if source is None:
            raise RuntimeError(f"Required safety source '{source_id}' is missing from the KB")
        return source
