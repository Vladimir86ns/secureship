"""Week 5 edge-case pass (Section 8): expired codes, malformed input, empty states, giving up mid-verification.

No test reaches a real model: services.chat.chat_completion is always an AsyncMock.
"""

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models import ChatSession, SessionState
from services.chat import build_system_prompt
from services.verification import generate_code, hash_code
from tests.conftest import FIXTURE_CUSTOMER
from tests.helpers import (
    get_session_row,
    history_text,
    text_message,
    tool_call_message,
    tool_results,
    verify_as,
)


# --- malformed input: verify_identity arguments (K1) -------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_identity_accepts_phone_number_sent_as_a_number(client: AsyncClient, db: AsyncSession, monkeypatch):
    identity = {**FIXTURE_CUSTOMER, "phone_number": 15550001111}
    mock_chat = AsyncMock(side_effect=[tool_call_message("verify_identity", identity), text_message("ok")])
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    resp = await client.post("/api/chat", json={"message": "where's my package?"})

    assert resp.status_code == 200
    assert tool_results(mock_chat) == [{"matched": True}]
    row = await get_session_row(db, client)
    assert row.pending_customer_id is not None
    assert row.pending_phone_number == "15550001111"


@pytest.mark.parametrize("bad_value", [["+15550001111"], {"number": "+15550001111"}, True])
@pytest.mark.asyncio
async def test_verify_identity_with_non_text_field_is_refused_not_a_500(
    client: AsyncClient, db: AsyncSession, monkeypatch, caplog, bad_value
):
    caplog.set_level(logging.INFO, logger="secureship.tools")
    identity = {**FIXTURE_CUSTOMER, "phone_number": bad_value}
    mock_chat = AsyncMock(side_effect=[tool_call_message("verify_identity", identity), text_message("ok")])
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    resp = await client.post("/api/chat", json={"message": "where's my package?"})

    assert resp.status_code == 200
    assert resp.json()["state"] == "anonymous"
    [result] = tool_results(mock_chat)
    assert result["error"] == "invalid_arguments"
    assert "plain text" in result["detail"]
    row = await get_session_row(db, client)
    assert row.pending_customer_id is None
    assert row.pending_first_name is None and row.pending_phone_number is None
    assert "tool DENIED name=verify_identity reason=invalid_arguments state=anonymous" in caplog.text
    assert "problem=identity_field_not_text" in caplog.text
    assert "phone_number:" in caplog.text  # the shape is logged ...
    assert "15550001111" not in caplog.text and "Testina" not in caplog.text  # ... never the values


@pytest.mark.asyncio
async def test_verify_identity_with_too_long_field_is_refused(client: AsyncClient, db: AsyncSession, monkeypatch):
    identity = {**FIXTURE_CUSTOMER, "address": "x" * 201}
    mock_chat = AsyncMock(side_effect=[tool_call_message("verify_identity", identity), text_message("ok")])
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    resp = await client.post("/api/chat", json={"message": "where's my package?"})

    assert resp.status_code == 200
    [result] = tool_results(mock_chat)
    assert result["error"] == "invalid_arguments"
    assert "200 characters" in result["detail"]
    row = await get_session_row(db, client)
    assert row.pending_address is None


@pytest.mark.asyncio
async def test_malformed_tool_call_entry_is_skipped_without_error(
    client: AsyncClient, db: AsyncSession, monkeypatch, caplog
):
    caplog.set_level(logging.INFO, logger="secureship.chat")
    mock_chat = AsyncMock(
        side_effect=[{"role": "assistant", "content": "", "tool_calls": ["x", {"function": "y"}]}]
    )
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    resp = await client.post("/api/chat", json={"message": "hello"})

    assert resp.status_code == 200
    assert resp.json()["messages"][-1]["role"] == "assistant"
    assert "reason=malformed_tool_call count=2" in caplog.text
    row = await get_session_row(db, client)
    assert row.state == SessionState.anonymous


# --- malformed input: request bodies (K2) ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_message_length_limit(client: AsyncClient, monkeypatch):
    mock_chat = AsyncMock(return_value=text_message("ok"))
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    too_long = await client.post("/api/chat", json={"message": "a" * 2001})
    assert too_long.status_code == 422
    mock_chat.assert_not_awaited()

    at_limit = await client.post("/api/chat", json={"message": "a" * 2000})
    assert at_limit.status_code == 200

    blank = await client.post("/api/chat", json={"message": "   "})
    assert blank.status_code == 400


@pytest.mark.parametrize("bad_code", ["12345", "abcdef", "1234567", "12 345", ""])
@pytest.mark.asyncio
async def test_malformed_code_is_rejected_without_using_an_attempt(
    client: AsyncClient, db: AsyncSession, monkeypatch, bad_code
):
    mock_chat = AsyncMock(
        side_effect=[
            tool_call_message("verify_identity", FIXTURE_CUSTOMER),
            tool_call_message("send_verification_code", {}),
            text_message("I've texted you a code."),
        ]
    )
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    await client.post("/api/chat", json={"message": "where's my package?"})

    resp = await client.post("/api/verify", json={"code": bad_code})

    assert resp.status_code == 422
    row = await get_session_row(db, client)
    await db.refresh(row)
    assert row.code_attempts == 0
    assert row.state == SessionState.awaiting_code


# --- expired codes (K3) ------------------------------------------------------------------------------------------


async def _to_awaiting_code(client: AsyncClient, monkeypatch) -> None:
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


async def _make_code_unusable(db: AsyncSession, client: AsyncClient, how: str) -> None:
    row = await get_session_row(db, client)
    if how == "expired":
        row.code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    else:
        row.code_attempts = row.code_max_attempts
    await db.commit()


def _tool_names(mock_chat) -> list[str]:
    return [t["function"]["name"] for t in mock_chat.await_args_list[0].args[2]]


@pytest.mark.parametrize("how,text", [("expired", "expired"), ("used_up", "too many incorrect")])
@pytest.mark.asyncio
async def test_unusable_code_restarts_verification_on_next_chat_message(
    client: AsyncClient, db: AsyncSession, monkeypatch, how, text
):
    await _to_awaiting_code(client, monkeypatch)
    await _make_code_unusable(db, client, how)
    mock_chat = AsyncMock(return_value=text_message("Sure — what are your details?"))
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    resp = await client.post("/api/chat", json={"message": "let's start over"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "collecting_identity"
    assert body["requires_code_modal"] is False
    notices = [m for m in body["messages"] if m["role"] == "system_event"]
    assert len(notices) == 1 and text in notices[0]["content"]
    assert "verify_identity" in _tool_names(mock_chat)  # the model can take new details in this same turn
    assert "lookup_shipments" not in _tool_names(mock_chat)

    row = await get_session_row(db, client)
    assert row.code_hash is None and row.code_expires_at is None and row.code_attempts == 0
    assert row.pending_customer_id is None and row.pending_phone_number is None
    assert row.customer_id is None and row.verified_at is None
    assert any(e.get("content") == "verification restarted" for e in row.transcript)


@pytest.mark.asyncio
async def test_valid_code_is_not_restarted_by_a_chat_message(client: AsyncClient, db: AsyncSession, monkeypatch):
    await _to_awaiting_code(client, monkeypatch)
    row = await get_session_row(db, client)
    code_hash = row.code_hash
    monkeypatch.setattr("services.chat.chat_completion", AsyncMock(return_value=text_message("Anything else?")))

    resp = await client.post("/api/chat", json={"message": "what are your opening hours?"})

    body = resp.json()
    assert body["state"] == "awaiting_code"
    assert body["requires_code_modal"] is True
    assert all(m["role"] != "system_event" for m in body["messages"])
    await db.refresh(row)
    assert row.code_hash == code_hash


@pytest.mark.asyncio
async def test_old_code_is_refused_after_restart(client: AsyncClient, db: AsyncSession, monkeypatch):
    await _to_awaiting_code(client, monkeypatch)
    row = await get_session_row(db, client)
    code = generate_code()
    row.code_hash = hash_code(code)
    await db.commit()
    await _make_code_unusable(db, client, "expired")
    monkeypatch.setattr("services.chat.chat_completion", AsyncMock(return_value=text_message("ok")))
    await client.post("/api/chat", json={"message": "hello again"})

    resp = await client.post("/api/verify", json={"code": code})

    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "no_pending_verification"
    await db.refresh(row)
    assert row.customer_id is None and row.state == SessionState.collecting_identity


@pytest.mark.asyncio
async def test_full_verification_works_again_after_restart(client: AsyncClient, db: AsyncSession, monkeypatch):
    await _to_awaiting_code(client, monkeypatch)
    await _make_code_unusable(db, client, "used_up")

    await verify_as(client, db, monkeypatch, FIXTURE_CUSTOMER)  # restart + verify_identity + code in one go

    row = await get_session_row(db, client)
    assert row.state == SessionState.verified and row.customer_id is not None


# --- giving up mid-verification (K4) -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_from_awaiting_code_goes_back_to_anonymous(client: AsyncClient, db: AsyncSession, monkeypatch):
    await _to_awaiting_code(client, monkeypatch)
    row = await get_session_row(db, client)
    code = generate_code()
    row.code_hash = hash_code(code)
    await db.commit()

    resp = await client.post("/api/verify/cancel")

    assert resp.status_code == 200
    assert resp.json() == {"state": "anonymous", "verified_at": None}
    await db.refresh(row)
    assert row.state == SessionState.anonymous
    assert row.code_hash is None and row.pending_customer_id is None and row.pending_first_name is None
    assert row.customer_id is None
    assert any(e.get("content") == "verification cancelled" and e.get("event") for e in row.transcript)
    assert row.transcript[-2]["content"] == "Verification cancelled." and "event" not in row.transcript[-2]

    refused = await client.post("/api/verify", json={"code": code})
    assert refused.status_code == 400
    assert refused.json()["detail"]["error"] == "no_pending_verification"

    session = (await client.get("/api/session")).json()
    assert session["requires_code_modal"] is False
    assert session["transcript"][-1]["content"] == "Verification cancelled."


@pytest.mark.asyncio
async def test_cancel_never_touches_a_verified_session(client: AsyncClient, db: AsyncSession, monkeypatch):
    await verify_as(client, db, monkeypatch, FIXTURE_CUSTOMER)
    row = await get_session_row(db, client)
    customer_id, verified_at = row.customer_id, row.verified_at

    resp = await client.post("/api/verify/cancel")

    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "already_verified"
    await db.refresh(row)
    assert row.state == SessionState.verified
    assert (row.customer_id, row.verified_at) == (customer_id, verified_at)

    mock_chat = AsyncMock(side_effect=[tool_call_message("lookup_shipments", {}), text_message("No shipments.")])
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    await client.post("/api/chat", json={"message": "my shipments?"})
    assert tool_results(mock_chat)[0]["count"] == 0  # lookup_shipments still allowed


@pytest.mark.asyncio
async def test_cancel_when_anonymous_changes_nothing(client: AsyncClient, db: AsyncSession):
    await client.get("/api/session")
    row = await get_session_row(db, client)
    transcript_before = list(row.transcript)

    resp = await client.post("/api/verify/cancel")

    assert resp.status_code == 200
    assert resp.json()["state"] == "anonymous"
    await db.refresh(row)
    assert row.customer_id is None and row.verified_at is None
    assert row.transcript == transcript_before


@pytest.mark.asyncio
async def test_cancel_from_collecting_identity_does_not_set_customer(
    client: AsyncClient, db: AsyncSession, monkeypatch
):
    mock_chat = AsyncMock(side_effect=[tool_call_message("verify_identity", FIXTURE_CUSTOMER), text_message("ok")])
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    await client.post("/api/chat", json={"message": "where's my package?"})
    row = await get_session_row(db, client)
    assert row.state == SessionState.collecting_identity and row.pending_customer_id is not None

    resp = await client.post("/api/verify/cancel")

    assert resp.json()["state"] == "anonymous"
    await db.refresh(row)
    assert row.pending_customer_id is None and row.customer_id is None


@pytest.mark.asyncio
async def test_new_topic_while_collecting_identity_keeps_state_and_gate(
    client: AsyncClient, db: AsyncSession, monkeypatch
):
    mock_chat = AsyncMock(side_effect=[tool_call_message("verify_identity", {"first_name": "Testina"}), text_message("ok")])
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    await client.post("/api/chat", json={"message": "I'm Testina"})
    row = await get_session_row(db, client)
    assert row.state == SessionState.anonymous  # missing fields: nothing stored, nothing moves

    mock_chat = AsyncMock(side_effect=[tool_call_message("verify_identity", FIXTURE_CUSTOMER), text_message("ok")])
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    await client.post("/api/chat", json={"message": "details"})
    mock_chat = AsyncMock(return_value=text_message("We're open 9 to 5."))
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    resp = await client.post("/api/chat", json={"message": "actually, what are your opening hours?"})

    assert resp.json()["state"] == "collecting_identity"
    assert "lookup_shipments" not in _tool_names(mock_chat)


@pytest.mark.asyncio
async def test_escalation_while_awaiting_code_resumes_awaiting_code(
    client: AsyncClient, db: AsyncSession, monkeypatch
):
    await _to_awaiting_code(client, monkeypatch)

    resp = await client.post("/api/chat", json={"message": "I want to talk to a human"})

    body = resp.json()
    assert body["state"] == "awaiting_code"
    assert body["requires_code_modal"] is True
    row = await get_session_row(db, client)
    assert row.customer_id is None


# --- empty states (K5) -------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verified_customer_without_shipments_gets_an_empty_result(
    client: AsyncClient, db: AsyncSession, monkeypatch, seeded, caplog
):
    caplog.set_level(logging.INFO, logger="secureship.tools")
    await verify_as(client, db, monkeypatch, FIXTURE_CUSTOMER)  # Testina has no shipments
    mock_chat = AsyncMock(
        side_effect=[tool_call_message("lookup_shipments", {}), text_message("There are no shipments yet.")]
    )
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    resp = await client.post("/api/chat", json={"message": "where are my shipments?"})

    assert resp.status_code == 200
    [result] = tool_results(mock_chat)
    assert result["count"] == 0 and result["shipments"] == []
    assert result["filtered_by_tracking_number"] is False
    assert "name=lookup_shipments scope=session.customer_id tracking_filter=no results=0" in caplog.text
    sent = history_text(mock_chat)
    assert not any(s["tracking_number"] in sent for s in seeded["data"]["shipments"])


def test_verified_prompt_covers_an_account_without_shipments():
    session = ChatSession(state=SessionState.verified, transcript=[])
    assert "no shipments on their account yet" in build_system_prompt(session)
    session.state = SessionState.anonymous
    assert "no shipments on their account yet" not in build_system_prompt(session)
