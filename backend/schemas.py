from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

CHAT_MESSAGE_MAX_LENGTH = 2000


EscalationStep = Literal["acknowledging", "color_shift", "human_joined", "reading_up", "greeting"]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant", "system_event"]
    content: str
    at: datetime
    # Section 6.2b: which step of the scripted human hand-off this message is (null for every other message).
    # The frontend changes the chat window color when the "color_shift" message is shown.
    escalation_step: EscalationStep | None = None


class ChatRequest(BaseModel):
    message: Annotated[str, StringConstraints(max_length=CHAT_MESSAGE_MAX_LENGTH)]


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
    # Checked before check_verification_code, so a malformed code never uses up an attempt.
    code: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{6}$")]


class VerifyResponse(BaseModel):
    state: str
    verified_at: datetime | None = None
