from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from dependencies import get_current_session
from models import ChatSession, Customer, SessionState
from schemas import SessionResponse
from services.transcript import visible_entries

router = APIRouter()


@router.get("/api/session", response_model=SessionResponse)
async def get_session(
    session: ChatSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    customer_first_name = None
    if session.customer_id:
        customer = await db.get(Customer, session.customer_id)
        customer_first_name = customer.first_name if customer else None

    await db.commit()

    return SessionResponse(
        state=session.state.value,
        verified_at=session.verified_at,
        escalated_to_human_at=session.escalated_to_human_at,
        customer_first_name=customer_first_name,
        requires_code_modal=session.state == SessionState.awaiting_code,
        transcript=visible_entries(session.transcript),
    )
