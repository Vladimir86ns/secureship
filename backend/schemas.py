from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ChatTurn(BaseModel):
    role: Literal["user", "assistant", "system_event"]
    content: str
    at: datetime


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    messages: list[ChatTurn]
    state: str
    verified_at: datetime | None = None
    escalated_to_human_at: datetime | None = None
    requires_code_modal: bool


class SessionResponse(BaseModel):
    state: str
    verified_at: datetime | None = None
    escalated_to_human_at: datetime | None = None
    customer_first_name: str | None = None
    requires_code_modal: bool
    transcript: list[ChatTurn]


class VerifyRequest(BaseModel):
    code: str


class VerifyResponse(BaseModel):
    state: str
    verified_at: datetime | None = None
