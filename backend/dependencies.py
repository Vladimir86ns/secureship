import secrets

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db import get_db
from models import ChatSession, SessionState

SESSION_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


async def get_current_session(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ChatSession:
    """Get-or-create by the httpOnly opaque session cookie. The cookie carries no
    claims — it's just a lookup key — so the frontend cannot forge or bypass
    verification state, which lives entirely in the row this resolves to.
    """
    token = request.cookies.get(settings.session_cookie_name)
    session = None
    if token:
        result = await db.execute(select(ChatSession).where(ChatSession.session_token == token))
        session = result.scalar_one_or_none()

    if session is None:
        token = secrets.token_urlsafe(32)
        session = ChatSession(session_token=token, state=SessionState.anonymous, transcript=[])
        db.add(session)
        await db.flush()
        response.set_cookie(
            key=settings.session_cookie_name,
            value=token,
            httponly=True,
            samesite="lax",
            secure=settings.session_cookie_secure,
            max_age=SESSION_COOKIE_MAX_AGE_SECONDS,
        )

    return session


def require_verified(session: ChatSession) -> None:
    """Not used by anything in Week 2. This is the hook Week 3's shipment tools
    (e.g. lookup_shipments) call before executing any real lookup.
    """
    if session.customer_id is None or session.verified_at is None:
        raise PermissionError("verification_required")
