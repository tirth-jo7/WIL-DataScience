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
        "keywords": ["oshc cover", "oshc benefits", "oshc mental health", "what does", "cover for"],
        "text": (
            "Medibank Comprehensive OSHC (RMIT's provider) includes benefits towards psychology, "
            "counselling, and mental health social worker services from recognised providers, as "
            "well as GP consultations related to a mental health management plan. It also covers "
            "emergency ambulance and eligible prescription medicines. Coverage isn't unlimited or "
            "automatic — check your policy for provider requirements and any gap fees."
        ),
        "source": {
            "title": "Medibank Comprehensive OSHC — Mental Health Support",
            "url": "https://www.medibank.com.au/overseas-health-insurance/oshc/comprehensive-oshc.htm",
        },
    },
    {
        "keywords": ["counselling helpline", "oshc counselling", "stress line", "24/7 student health", "24/7 helpline"],
        "text": (
            "If you're a Medibank OSHC member, you can call the 24/7 Student Health and Support Line "
            "on 1800 887 283 for medical assistance from a registered nurse, stress and trauma "
            "counselling services, and help navigating the health system."
        ),
        "source": {
            "title": "24/7 Student Health and Support Line (Medibank OSHC)",
            "url": "https://www.rmit.edu.au/study-with-us/international-students/apply-to-rmit-international-students/student-visas/health-cover-requirements",
        },
    },
    {
        "keywords": ["oshc", "health cover", "health insurance", "overseas student health"],
        "text": (
            "As an international student on an Australian student visa, you're required to hold "
            "valid Overseas Student Health Cover (OSHC) with an approved provider for the entire "
            "duration of your visa. RMIT arranges Medibank Comprehensive OSHC on your behalf when "
            "you accept your offer, or you can use your own approved provider."
        ),
        "source": {
            "title": "Overseas Student Health Cover requirements",
            "url": "https://www.rmit.edu.au/study-with-us/international-students/apply-to-rmit-international-students/student-visas/health-cover-requirements",
        },
    },
    {
        "keywords": ["counselling", "counsellor", "therapy", "psychologist", "mental health support"],
        "text": (
            "RMIT Counselling and Psychological Services offers free, confidential, short-term "
            "counselling to all currently enrolled RMIT students located in Australia, including "
            "international students, covering issues like anxiety, depression, and stress."
        ),
        "source": {
            "title": "RMIT Counselling and Psychological Services",
            "url": "https://www.rmit.edu.au/students/support-and-facilities/student-support/counselling",
        },
    },
    {
        "keywords": ["offshore", "exchange", "outside australia", "overseas student located"],
        "text": (
            "If you're an RMIT student currently located outside Australia, on-campus counselling "
            "isn't available due to Australian health regulatory law. Students on exchange can call "
            "RMIT International SOS on +61 2 9372 2468, and international students located offshore "
            "can call Medibank on +61 2 8905 0307 for phone-based mental health support advice."
        ),
        "source": {
            "title": "RMIT Counselling and Psychological Services",
            "url": "https://www.rmit.edu.au/students/support-and-facilities/student-support/counselling",
        },
    },
    {
        "keywords": ["international student", "support services", "eligibility", "new to rmit"],
        "text": (
            "RMIT provides a dedicated support hub for international students covering health, "
            "careers, study and English language support, and events, in addition to general RMIT "
            "student support services available to all students."
        ),
        "source": {
            "title": "International students — RMIT Support Services",
            "url": "https://www.rmit.edu.au/students/support-services/international-students.html",
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