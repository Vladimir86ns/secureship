import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from config import settings
from models import ChatSession, SessionState
from services.mock_sms import send_mock_sms
from services.transcript import append_internal_event, transition_state


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def code_matches(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_code(code), code_hash)


def dispatch_verification_code(session: ChatSession) -> dict:
    """Generate, store (hashed), and 'send' a fresh code. Used by both the
    send_verification_code tool and POST /api/verify/resend.
    """
    if session.pending_customer_id is None:
        return {"error": "no_pending_identity"}

    code = generate_code()
    session.code_hash = hash_code(code)
    session.code_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.verification_code_ttl_seconds
    )
    session.code_attempts = 0
    session.code_max_attempts = settings.verification_max_attempts
    session.code_last_sent_at = datetime.now(timezone.utc)

    transition_state(session, SessionState.code_sent)
    send_mock_sms(session.pending_phone_number or "", code)
    transition_state(session, SessionState.awaiting_code)

    phone = session.pending_phone_number or ""
    return {
        "sent": True,
        "phone_last4": phone[-4:],
        "expires_in_seconds": settings.verification_code_ttl_seconds,
    }


def check_verification_code(session: ChatSession, code: str) -> dict:
    """Backend-only — invoked exclusively by POST /api/verify. Never an LLM tool,
    so verification-flipping code is architecturally unreachable from the model.
    """
    if session.state != SessionState.awaiting_code or not session.code_hash:
        return {"ok": False, "error": "no_pending_verification"}

    now = datetime.now(timezone.utc)

    if session.code_expires_at and now > session.code_expires_at:
        append_internal_event(session, "system_event", "code expired", event="verification_outcome")
        return {"ok": False, "error": "code_expired"}

    if session.code_attempts >= session.code_max_attempts:
        append_internal_event(
            session, "system_event", "max attempts reached", event="verification_outcome"
        )
        return {"ok": False, "error": "too_many_attempts"}

    if not code_matches(code, session.code_hash):
        session.code_attempts += 1
        append_internal_event(
            session, "system_event", "incorrect code attempt", event="verification_outcome"
        )
        return {
            "ok": False,
            "error": "invalid_code",
            "attempts_remaining": session.code_max_attempts - session.code_attempts,
        }

    session.customer_id = session.pending_customer_id
    session.pending_customer_id = None
    session.code_hash = None
    session.code_expires_at = None
    session.verified_at = now
    transition_state(session, SessionState.verified)
    append_internal_event(session, "system_event", "verification succeeded", event="verification_outcome")
    return {"ok": True}


def resend_verification_code(session: ChatSession) -> dict:
    if session.code_last_sent_at:
        elapsed = (datetime.now(timezone.utc) - session.code_last_sent_at).total_seconds()
        if elapsed < settings.verification_resend_cooldown_seconds:
            return {
                "ok": False,
                "error": "cooldown",
                "retry_after_seconds": int(settings.verification_resend_cooldown_seconds - elapsed),
            }

    result = dispatch_verification_code(session)
    if "error" in result:
        return {"ok": False, "error": result["error"]}
    return {"ok": True, **result}
