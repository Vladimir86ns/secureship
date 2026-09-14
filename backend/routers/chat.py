from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from dependencies import get_current_session
from models import ChatSession, SessionState
from schemas import ChatRequest, ChatResponse
from services.chat import handle_chat_turn

router = APIRouter()


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    session: ChatSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")

    turns = await handle_chat_turn(db, session, payload.message)
    await db.commit()

    return ChatResponse(
        messages=turns,
        state=session.state.value,
        verified_at=session.verified_at,
        escalated_to_human_at=session.escalated_to_human_at,
        requires_code_modal=session.state == SessionState.awaiting_code,
    )
