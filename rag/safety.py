from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SafetyRoute = Literal["normal", "crisis", "clinical", "prompt_injection"]


@dataclass(frozen=True)
class SafetyDecision:
    route: SafetyRoute
    reason: str | None = None


_CRISIS_PATTERNS = (
    r"\bcrisis\b",
    r"\burgent (?:mental health |wellbeing )?(?:help|support)\b",
    r"\bimmediate danger\b",
    r"\bin danger\b",
    r"\bnot safe (?:right now|at the moment|currently)?\b",
    r"\bdon'?t feel safe\b",
    r"\bcan'?t stay safe\b",
    r"\bemergency\b",
    r"\bneed help (?:right )?now\b",
    r"\bhelp tonight\b",
    r"\bsuicid(?:e|al)\b",
    r"\bself[- ]?harm\b",
)

_CLINICAL_PATTERNS = (
    r"\bdiagnos(?:e|ed|ing|is)\b",
    r"\bwhat (?:mental health )?(?:condition|disorder) do i have\b",
    r"\bwhat medication should i (?:take|use)\b",
    r"\bwhat medicine should i (?:take|use)\b",
    r"\bwhat dose should i take\b",
    r"\bprescribe\b",
)

_INJECTION_PATTERNS = (
    r"ignore (?:all |the )?(?:previous|system) instructions",
    r"reveal (?:the )?system prompt",
    r"show (?:me )?(?:your|the) hidden instructions",
    r"pretend (?:the )?(?:rules|instructions) do not apply",
)


def classify_input(text: str) -> SafetyDecision:
    normalized = " ".join(text.lower().split())

    for pattern in _CRISIS_PATTERNS:
        if re.search(pattern, normalized):
            return SafetyDecision("crisis", "urgent-safety-signal")

    for pattern in _CLINICAL_PATTERNS:
        if re.search(pattern, normalized):
            return SafetyDecision("clinical", "clinical-advice-request")

    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, normalized):
            return SafetyDecision("prompt_injection", "instruction-override-attempt")

    return SafetyDecision("normal")
