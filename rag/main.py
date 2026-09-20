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


@app.post("/query")
def query(request: RagRequest):

    print("\n📨 REQUEST RECEIVED")
    print(request.model_dump())

    text = request.message.text.lower()

    if "crisis" in text or "suicide" in text:
        response = {
            "text": (
                "If you are in immediate danger or need urgent "
                "support, please contact an appropriate crisis "
                "service or emergency service."
            ),
            "type": "crisis",
            "confidence": 0.98,
            "crisisDetected": True,
        }

    else:
        response = {
            "text": (
                "Based on your message, a university wellbeing "
                "or counselling service may be a suitable place "
                "to start. I can help you find the relevant "
                "support service."
            ),
            "type": "navigation",
            "confidence": 0.91,
            "crisisDetected": False,
        }

    return {
        "requestId": request.requestId,

        "response": {
            "text": response["text"],
        },

        "classification": {
            "type": response["type"],
            "confidence": response["confidence"],
        },

        "sources": [
            {
                "title": "University Wellbeing Service",
                "url": "https://example.com/wellbeing",
            }
        ],

        "safety": {
            "crisisDetected": response["crisisDetected"],
            "clinicalAdvice": False,
        },
    }