from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class User(BaseModel):
    id: int
    username: str | None = None
    firstName: str | None = None


class Message(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    timestamp: str


class RagRequest(BaseModel):
    requestId: str
    channel: Literal["telegram"]
    user: User
    message: Message


class Source(BaseModel):
    id: str
    title: str
    url: str
    content: str
    tags: list[str] = Field(default_factory=list)
    last_verified: str | None = None


class RetrievedSource(Source):
    score: float = Field(ge=0.0, le=1.0)
    raw_score: float = Field(ge=0.0)


class LLMAnswer(BaseModel):
    text: str = Field(min_length=1, max_length=1800)
    type: Literal["navigation", "crisis", "unsupported"]
    confidence: float = Field(ge=0.0, le=1.0)
    source_ids: list[str] = Field(default_factory=list)
    clinicalAdvice: bool = False


class RagSource(BaseModel):
    title: str
    url: str


class ResponseBody(BaseModel):
    text: str


class Classification(BaseModel):
    type: Literal["navigation", "crisis", "unsupported"]
    confidence: float = Field(ge=0.0, le=1.0)


class SafetyMetadata(BaseModel):
    crisisDetected: bool
    clinicalAdvice: bool


class RagResponse(BaseModel):
    requestId: str
    response: ResponseBody
    classification: Classification
    sources: list[RagSource]
    safety: SafetyMetadata
