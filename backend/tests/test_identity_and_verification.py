from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import ChatSession, SessionState
from services.chat import _tool_verify_identity
from services.verification import dispatch_verification_code
from tests.conftest import FIXTURE_CUSTOMER
from tests.helpers import text_message, tool_call_message


async def _get_session_row(db: AsyncSession, client: AsyncClient) -> ChatSession:
    token = client.cookies.get(settings.session_cookie_name)
    result = await db.execute(select(ChatSession).where(ChatSession.session_token == token))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_verify_identity_match_sets_pending_customer_not_customer(
    client: AsyncClient, db: AsyncSession, monkeypatch
):
    mock_chat = AsyncMock(
        side_effect=[
            tool_call_message("verify_identity", FIXTURE_CUSTOMER),
            tool_call_message("send_verification_code", {}),
            text_message("I've texted you a code."),
        ]
    )
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    resp = await client.post("/api/chat", json={"message": "where's my package?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "awaiting_code"
    assert body["requires_code_modal"] is True

    row = await _get_session_row(db, client)
    assert row.pending_customer_id is not None
    assert row.customer_id is None  # not promoted yet — only check_verification_code does that
    assert row.code_hash is not None


@pytest.mark.asyncio
async def test_verify_identity_no_match_stays_neutral(client: AsyncClient, db: AsyncSession, monkeypatch):
    made_up = {
        "first_name": "Nobody",
        "last_name": "Fake",
        "address": "1 Nowhere Ave",
        "phone_number": "555-000-0000",
    }
    mock_chat = AsyncMock(
        side_effect=[
            tool_call_message("verify_identity", made_up),
            text_message("I wasn't able to verify those details — could you double-check and try again?"),
        ]
    )
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    resp = await client.post(
        "/api/chat", json={"message": "where's my package? Nobody Fake, 1 Nowhere Ave, 555-000-0000"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "collecting_identity"
    assert body["requires_code_modal"] is False
    # neutral: no field-level detail leaked
    reply_text = " ".join(m["content"] for m in body["messages"])
    assert "field" not in reply_text.lower()

    row = await _get_session_row(db, client)
    assert row.pending_customer_id is None
    assert row.customer_id is None


async def _reach_awaiting_code(client: AsyncClient, monkeypatch) -> None:
    mock_chat = AsyncMock(
        side_effect=[
            tool_call_message("verify_identity", FIXTURE_CUSTOMER),
            tool_call_message("send_verification_code", {}),
            text_message("I've texted you a code."),
        ]
    )
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    resp = await client.post("/api/chat", json={"message": "where's my package?"})
    assert resp.json()["state"] == "awaiting_code"


@pytest.mark.asyncio
async def test_verify_correct_code_promotes_customer_id(client: AsyncClient, db: AsyncSession, monkeypatch):
    await _reach_awaiting_code(client, monkeypatch)

    from services.verification import generate_code, hash_code

    row = await _get_session_row(db, client)
    code = generate_code()
    row.code_hash = hash_code(code)
    await db.commit()

    resp = await client.post("/api/verify", json={"code": code})
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "verified"
    assert body["verified_at"] is not None

    final_row = await _get_session_row(db, client)
    assert final_row.customer_id is not None
    assert final_row.pending_customer_id is None
    assert final_row.code_hash is None


@pytest.mark.asyncio
async def test_verify_wrong_code_increments_attempts(client: AsyncClient, db: AsyncSession, monkeypatch):
    await _reach_awaiting_code(client, monkeypatch)

    resp = await client.post("/api/verify", json={"code": "000000"})
    assert resp.status_code == 400
    row = await _get_session_row(db, client)
    assert row.code_attempts == 1
    assert row.state == SessionState.awaiting_code


@pytest.mark.asyncio
async def test_verify_max_attempts_then_resend_recovers(client: AsyncClient, db: AsyncSession, monkeypatch):
    await _reach_awaiting_code(client, monkeypatch)

    for _ in range(5):
        resp = await client.post("/api/verify", json={"code": "000000"})
        assert resp.status_code == 400

    resp = await client.post("/api/verify", json={"code": "000000"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "too_many_attempts"

    row = await _get_session_row(db, client)
    assert row.code_last_sent_at is not None
    row.code_last_sent_at = None
    await db.commit()

    resend_resp = await client.post("/api/verify/resend")
    assert resend_resp.status_code == 200
    row = await _get_session_row(db, client)
    assert row.code_attempts == 0


@pytest.mark.asyncio
async def test_verify_expired_code(client: AsyncClient, db: AsyncSession, monkeypatch):
    await _reach_awaiting_code(client, monkeypatch)

    row = await _get_session_row(db, client)
    row.code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()

    resp = await client.post("/api/verify", json={"code": "000000"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "code_expired"

    row = await _get_session_row(db, client)
    assert row.state == SessionState.awaiting_code
    assert row.customer_id is None


@pytest.mark.asyncio
async def test_tool_verify_identity_missing_fields_returns_error_without_side_effects(db: AsyncSession):
    session = ChatSession(state=SessionState.anonymous, transcript=[])
    incomplete_args = {
        "first_name": FIXTURE_CUSTOMER["first_name"],
        "last_name": FIXTURE_CUSTOMER["last_name"],
        "address": FIXTURE_CUSTOMER["address"],
        "phone_number": "",  # missing
    }

    result = await _tool_verify_identity(db, session, incomplete_args)

    assert result == {"error": "missing_fields", "missing": ["phone_number"]}
    # No side effects: state doesn't advance, nothing pending is recorded.
    assert session.state == SessionState.anonymous
    assert session.pending_customer_id is None
    assert session.pending_first_name is None


def test_dispatch_verification_code_refuses_without_pending_customer():
    session = ChatSession(state=SessionState.collecting_identity, transcript=[])

    result = dispatch_verification_code(session)

    assert result == {"error": "no_pending_identity"}
    assert session.code_hash is None
    assert session.state == SessionState.collecting_identity


@pytest.mark.asyncio
async def test_send_verification_code_tool_refuses_when_called_out_of_order(
    client: AsyncClient, db: AsyncSession, monkeypatch
):
    # The model tries to send a code without ever having matched an identity first.
    mock_chat = AsyncMock(
        side_effect=[
            tool_call_message("send_verification_code", {}),
            text_message("Let me get your details first."),
        ]
    )
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    resp = await client.post("/api/chat", json={"message": "send me a code"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "anonymous"
    assert resp.json()["requires_code_modal"] is False

    row = await _get_session_row(db, client)
    assert row.code_hash is None
    assert row.state == SessionState.anonymous
