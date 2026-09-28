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


# Match Markdown links such as:
# [RMIT Counselling](https://www.rmit.edu.au/...)
_MARKDOWN_LINK_RE = re.compile(
    r"\[([^\]]+)\]\(https?://[^)\s]+\)",
    re.IGNORECASE,
)

# Match normal URLs appearing in generated prose.
_URL_RE = re.compile(
    r"https?://[^\s<>()]+",
    re.IGNORECASE,
)


def _sanitize_answer_text(text: str) -> str:
    """
    Remove model-generated URLs from free-text answers.

    Verified URLs are returned separately from the knowledge base
    in the structured `sources` field.
    """

    # Keep Markdown link text but remove the URL.
    # Example:
    # [RMIT Counselling](https://...) -> RMIT Counselling
    text = _MARKDOWN_LINK_RE.sub(r"\1", text)

    # Remove any remaining plain URLs.
    text = _URL_RE.sub("", text)

    # Clean spacing left behind.
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


class Generator(Protocol):
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMAnswer:
        ...


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

    async def handle(
        self,
        request: RagRequest,
    ) -> RagResponse:

        question = request.message.text.strip()

        # ------------------------------------------------------------
        # 1. Deterministic safety pre-check
        # ------------------------------------------------------------

        safety = classify_input(question)

        if safety.route == "crisis":
            return self._crisis_response(
                request.requestId
            )

        if safety.route == "clinical":
            return self._clinical_scope_response(
                request.requestId
            )

        if safety.route == "prompt_injection":
            return self._unsupported_response(
                request.requestId,
                (
                    "I can help with finding verified student wellbeing "
                    "support services, but I can't follow requests to "
                    "override the assistant's safety or source rules."
                ),
            )

        # ------------------------------------------------------------
        # 2. Retrieve relevant verified sources
        # ------------------------------------------------------------

        retrieved = self.retriever.retrieve(
            question,
            top_k=self.top_k,
        )

        if (
            not retrieved
            or retrieved[0].score < self.min_retrieval_score
        ):
            return self._unsupported_response(
                request.requestId,
                (
                    "I couldn't find enough verified information in the "
                    "wellbeing knowledge base to answer that safely. "
                    "Try describing the kind of support you are looking for."
                ),
            )

        # ------------------------------------------------------------
        # 3. Build grounded RAG prompt
        # ------------------------------------------------------------

        user_prompt = build_user_prompt(
            question,
            retrieved,
        )

        # ------------------------------------------------------------
        # 4. Generate response with Ollama
        # ------------------------------------------------------------

        try:
            generated = await self.generator.generate(
                SYSTEM_PROMPT,
                user_prompt,
            )

        except Exception:
            return self._unsupported_response(
                request.requestId,
                (
                    "I couldn't generate a grounded answer right now. "
                    "Please use the verified support links provided by "
                    "the university directly."
                ),
            )

        # ------------------------------------------------------------
        # 5. Post-generation safety checks
        # ------------------------------------------------------------

        # If the model identifies urgency that the deterministic
        # pre-check missed, use the fixed application response.
        if generated.type == "crisis":
            return self._crisis_response(
                request.requestId
            )

        # Reject clinical advice.
        if generated.clinicalAdvice:
            return self._clinical_scope_response(
                request.requestId
            )

        # Respect model uncertainty when it cannot support an answer.
        if generated.type == "unsupported":
            return self._unsupported_response(
                request.requestId,
                generated.text,
            )

        # ------------------------------------------------------------
        # 6. Validate source attribution
        # ------------------------------------------------------------

        retrieved_by_id = {
            source.id: source
            for source in retrieved
        }

        # Remove duplicate source IDs while preserving order.
        allowed_ids = list(
            dict.fromkeys(generated.source_ids)
        )

        selected = [
            retrieved_by_id[source_id]
            for source_id in allowed_ids
            if source_id in retrieved_by_id
        ]

        # Fail closed if the LLM invents a source ID or gives
        # a navigation answer without a valid source.
        if (
            len(selected) != len(allowed_ids)
            or not selected
        ):
            return self._unsupported_response(
                request.requestId,
                (
                    "I couldn't verify the sources for that answer, "
                    "so I won't present it as supported information."
                ),
            )

        # ------------------------------------------------------------
        # 7. Sanitize model-generated URLs
        # ------------------------------------------------------------

        # URLs should only appear in the structured source list.
        # Small local models can sometimes echo source URLs even when
        # instructed not to. We remove them from prose rather than
        # rejecting an otherwise grounded answer.
        answer_text = _sanitize_answer_text(
            generated.text
        )

        if not answer_text:
            return self._unsupported_response(
                request.requestId,
                (
                    "I couldn't produce a safely formatted grounded "
                    "answer from the verified sources."
                ),
            )

        # ------------------------------------------------------------
        # 8. Return validated grounded response
        # ------------------------------------------------------------

        return RagResponse(
            requestId=request.requestId,

            response=ResponseBody(
                text=answer_text
            ),

            classification=Classification(
                type="navigation",
                confidence=generated.confidence,
            ),

            sources=[
                RagSource(
                    title=source.title,
                    url=source.url,
                )
                for source in selected
            ],

            safety=SafetyMetadata(
                crisisDetected=False,
                clinicalAdvice=False,
            ),
        )

    def _crisis_response(
        self,
        request_id: str,
    ) -> RagResponse:

        source = self._required_source(
            "emergency_crisis"
        )

        text = (
            "For urgent mental health support, use RMIT's "
            "verified urgent-support service. If there is immediate "
            "danger in Australia, contact emergency services."
        )

        return RagResponse(
            requestId=request_id,

            response=ResponseBody(
                text=text
            ),

            classification=Classification(
                type="crisis",
                confidence=1.0,
            ),

            sources=[
                RagSource(
                    title=source.title,
                    url=source.url,
                )
            ],

            safety=SafetyMetadata(
                crisisDetected=True,
                clinicalAdvice=False,
            ),
        )

    def _clinical_scope_response(
        self,
        request_id: str,
    ) -> RagResponse:

        source = self.retriever.get_source(
            "counselling"
        )

        sources = (
            [
                RagSource(
                    title=source.title,
                    url=source.url,
                )
            ]
            if source
            else []
        )

        return RagResponse(
            requestId=request_id,

            response=ResponseBody(
                text=(
                    "I can help you find support services, but I can't "
                    "diagnose a condition, prescribe treatment, or "
                    "recommend medication. A qualified health professional "
                    "or RMIT counselling service can discuss your concerns "
                    "with you."
                )
            ),

            classification=Classification(
                type="unsupported",
                confidence=1.0,
            ),

            sources=sources,

            safety=SafetyMetadata(
                crisisDetected=False,
                clinicalAdvice=False,
            ),
        )

    def _unsupported_response(
        self,
        request_id: str,
        text: str,
    ) -> RagResponse:

        return RagResponse(
            requestId=request_id,

            response=ResponseBody(
                text=text
            ),

            classification=Classification(
                type="unsupported",
                confidence=1.0,
            ),

            sources=[],

            safety=SafetyMetadata(
                crisisDetected=False,
                clinicalAdvice=False,
            ),
        )

    def _required_source(
        self,
        source_id: str,
    ) -> Source:

        source = self.retriever.get_source(
            source_id
        )

        if source is None:
            raise RuntimeError(
                f"Required safety source "
                f"'{source_id}' is missing from the KB"
            )

        return source