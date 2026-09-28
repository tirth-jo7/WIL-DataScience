from fastapi.testclient import TestClient

from rag.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_crisis_api_contract() -> None:
    response = client.post(
        "/query",
        json={
            "requestId": "abc-123",
            "channel": "telegram",
            "user": {"id": 42, "username": "student", "firstName": "Sam"},
            "message": {
                "text": "I need urgent mental health support and don't feel safe right now.",
                "timestamp": "2026-09-28T00:00:00Z"
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requestId"] == "abc-123"
    assert payload["classification"]["type"] == "crisis"
    assert payload["safety"]["crisisDetected"] is True
    assert payload["safety"]["clinicalAdvice"] is False
    assert payload["sources"][0]["url"].startswith("https://www.rmit.edu.au/")
