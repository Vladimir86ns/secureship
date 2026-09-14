from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import ChatSession, SessionState
from services.verification import generate_code, hash_code
from tests.conftest import FIXTURE_CUSTOMER
from tests.helpers import text_message, tool_call_message


async def _get_session_row(db: AsyncSession, client: AsyncClient) -> ChatSession:
    token = client.cookies.get(settings.session_cookie_name)
    result = await db.execute(select(ChatSession).where(ChatSession.session_token == token))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_escalation_triggers_once_and_produces_expected_sequence(
    client: AsyncClient, db: AsyncSession, monkeypatch
):
    mock_chat = AsyncMock()
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    resp = await client.post("/api/chat", json={"message": "I want to talk to a human"})
    assert resp.status_code == 200
    body = resp.json()

    # Escalation never calls the LLM.
    mock_chat.assert_not_awaited()

    contents = [m["content"] for m in body["messages"]]
    assert any("connect" in c.lower() for c in contents)
    assert any("joined the chat" in c.lower() for c in contents)
    assert body["escalated_to_human_at"] is not None

    row = await _get_session_row(db, client)
    assert row.escalated_agent_name is not None
    # State resumed back to anonymous after the scripted hand-off completed.
    assert row.state == SessionState.anonymous

    # A second "talk to human" message doesn't re-trigger the intro sequence.
    mock_chat.side_effect = [text_message("Sure, how can I help?")]
    resp2 = await client.post("/api/chat", json={"message": "can I speak to a human again please"})
    assert resp2.status_code == 200
    contents2 = [m["content"] for m in resp2.json()["messages"]]
    assert not any("joined the chat" in c.lower() for c in contents2)


@pytest.mark.asyncio
async def test_escalation_does_not_bypass_gating(client: AsyncClient, db: AsyncSession, monkeypatch):
    mock_chat = AsyncMock()
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    await client.post("/api/chat", json={"message": "I want to talk to a human"})

    row = await _get_session_row(db, client)
    assert row.customer_id is None
    assert row.verified_at is None

    mock_chat.side_effect = [
        tool_call_message("verify_identity", FIXTURE_CUSTOMER),
        tool_call_message("send_verification_code", {}),
        text_message("I've texted you a code."),
    ]
    resp = await client.post("/api/chat", json={"message": "where's my package?"})
    assert resp.json()["state"] == "awaiting_code"

    row = await _get_session_row(db, client)
    assert row.customer_id is None  # still not verified — escalation didn't skip the flow
    assert row.pending_customer_id is not None


@pytest.mark.asyncio
async def test_escalation_from_verified_state_resumes_verified_and_keeps_it(
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
    assert resp.json()["state"] == "awaiting_code"

    row = await _get_session_row(db, client)
    code = generate_code()
    row.code_hash = hash_code(code)
    await db.commit()
    verify_resp = await client.post("/api/verify", json={"code": code})
    assert verify_resp.json()["state"] == "verified"

    # Now escalate from the verified state. Reset call tracking (the mock was
    # already awaited 3 times above) so assert_not_awaited below is meaningful.
    mock_chat.reset_mock(side_effect=True)
    resp2 = await client.post("/api/chat", json={"message": "I want to talk to a human"})
    assert resp2.status_code == 200
    body2 = resp2.json()

    mock_chat.assert_not_awaited()  # escalation still never calls the LLM
    contents = [m["content"] for m in body2["messages"]]
    assert any("joined the chat" in c.lower() for c in contents)
    # Personalized greeting, using the identity given during the earlier turn.
    assert any(FIXTURE_CUSTOMER["first_name"] in c for c in contents)

    row = await _get_session_row(db, client)
    # State resumed to verified, not stuck at escalated_to_human, and the
    # underlying verification facts are untouched by the hand-off.
    assert row.state == SessionState.verified
    assert row.customer_id is not None
    assert row.verified_at is not None
    assert body2["state"] == "verified"
    assert body2["verified_at"] is not None
