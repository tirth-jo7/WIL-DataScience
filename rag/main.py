from fastapi import FastAPI
from pydantic import BaseModel
from typing import Literal


app = FastAPI(
    title="Student Wellbeing RAG",
)


class User(BaseModel):
    id: int
    username: str | None = None
    firstName: str | None = None


class Message(BaseModel):
    text: str
    timestamp: str


class RagRequest(BaseModel):
    requestId: str
    channel: Literal["telegram"]
    user: User
    message: Message


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


INTERNATIONAL_KB = [
    {
        "keywords": ["oshc", "health cover", "overseas student health"],
        "text": (
            "As an international student, your Overseas Student Health "
            "Cover (OSHC) includes access to mental health support. "
            "You can use OSHC to see a GP who can refer you to a "
            "psychologist or counsellor, often at reduced or no cost "
            "depending on your policy."
        ),
        "source": {
            "title": "OSHC Mental Health Support",
            "url": "https://example.com/oshc-mental-health",
        },
    },
    {
        "keywords": ["international student", "visa", "eligibility"],
        "text": (
            "International students can access the university's free "
            "on-campus counselling service regardless of their OSHC "
            "provider. This is separate from and in addition to any "
            "cover included in your health insurance."
        ),
        "source": {
            "title": "International Student Support Services",
            "url": "https://example.com/international-support",
        },
    },
]


def search_international_kb(text: str):
    text_lower = text.lower()
    for entry in INTERNATIONAL_KB:
        if any(keyword in text_lower for keyword in entry["keywords"]):
            return entry
    return None


@app.post("/query")
def query(request: RagRequest):

    print("\n📨 REQUEST RECEIVED")
    print(request.model_dump())

    text = request.message.text.lower()

    # Crisis check (existing logic, untouched)
    if "crisis" in text or "suicide" in text:
        response_text = (
            "If you are in immediate danger or need urgent "
            "support, please contact an appropriate crisis "
            "service or emergency service."
        )
        response_type = "crisis"
        confidence = 0.98
        crisis_detected = True
        sources = [{"title": "University Wellbeing Service", "url": "https://example.com/wellbeing"}]

    else:
        # check international student KB first
        kb_match = search_international_kb(text)

        if kb_match:
            response_text = kb_match["text"]
            response_type = "navigation"
            confidence = 0.9
            crisis_detected = False
            sources = [kb_match["source"]]
        else:
            response_text = (
                "Based on your message, a university wellbeing "
                "or counselling service may be a suitable place "
                "to start. I can help you find the relevant "
                "support service."
            )
            response_type = "navigation"
            confidence = 0.91
            crisis_detected = False
            sources = [{"title": "University Wellbeing Service", "url": "https://example.com/wellbeing"}]

    return {
        "requestId": request.requestId,

        "response": {
            "text": response_text,
        },

        "classification": {
            "type": response_type,
            "confidence": confidence,
        },

        "sources": sources,

        "safety": {
            "crisisDetected": crisis_detected,
            "clinicalAdvice": False,
        },
    }