from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from dependencies import get_current_session
from models import ChatSession
from schemas import VerifyRequest, VerifyResponse
from services.verification import check_verification_code, resend_verification_code

router = APIRouter()

_ERROR_STATUS = {
    "no_pending_verification": 400,
    "code_expired": 400,
    "too_many_attempts": 400,
    "invalid_code": 400,
    "no_pending_identity": 400,
}


@router.post("/api/verify", response_model=VerifyResponse)
async def verify(
    payload: VerifyRequest,
    session: ChatSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> VerifyResponse:
    result = check_verification_code(session, payload.code)
    await db.commit()

    if not result.get("ok"):
        raise HTTPException(
            status_code=_ERROR_STATUS.get(result["error"], 400),
            detail={"error": result["error"], "attempts_remaining": result.get("attempts_remaining")},
        )

    return VerifyResponse(state=session.state.value, verified_at=session.verified_at)


@router.post("/api/verify/resend", response_model=VerifyResponse)
async def resend(
    session: ChatSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> VerifyResponse:
    result = resend_verification_code(session)
    await db.commit()

    if not result.get("ok"):
        status_code = 429 if result["error"] == "cooldown" else _ERROR_STATUS.get(result["error"], 400)
        raise HTTPException(
            status_code=status_code,
            detail={"error": result["error"], "retry_after_seconds": result.get("retry_after_seconds")},
        )

    return VerifyResponse(state=session.state.value, verified_at=session.verified_at)
