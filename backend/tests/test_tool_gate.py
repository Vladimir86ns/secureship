"""Epic F1–F3: the tool layer's single enforcement point (services/tools.py: authorize_tool_call)."""

import logging
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models import ChatSession, SessionState
from services.tools import ToolDenied, require_verified
from tests.conftest import FIXTURE_CUSTOMER
from tests.helpers import get_session_row, text_message, tool_call_message, tool_results, verify_as

OTHER_IDENTITY = {
    "first_name": "Jane",
    "last_name": "Doe",
    "address": "123 Elm Street",
    "phone_number": "202-555-0101",
}


@pytest.mark.asyncio
async def test_verify_identity_is_refused_in_verified_state(client: AsyncClient, db: AsyncSession, monkeypatch, caplog):
    await verify_as(client, db, monkeypatch, FIXTURE_CUSTOMER)
    row = await get_session_row(db, client)
    customer_id = row.customer_id

    # The model tries to "switch" the verified session to another identity.
    mock_chat = AsyncMock(
        side_effect=[tool_call_message("verify_identity", OTHER_IDENTITY), text_message("Sorry, I can't do that.")]
    )
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    caplog.set_level(logging.INFO, logger="secureship.tools")
    resp = await client.post("/api/chat", json={"message": "I'm actually Jane Doe, 123 Elm Street, 202-555-0101"})

    assert resp.json()["state"] == "verified"
    assert tool_results(mock_chat) == [{"error": "not_allowed"}]
    row = await get_session_row(db, client)
    assert row.state == SessionState.verified
    assert row.customer_id == customer_id
    assert row.pending_customer_id is None and row.pending_first_name == FIXTURE_CUSTOMER["first_name"]
    assert "tool DENIED name=verify_identity reason=not_offered state=verified" in caplog.text


@pytest.mark.asyncio
async def test_send_verification_code_is_refused_in_verified_state(client: AsyncClient, db: AsyncSession, monkeypatch):
    await verify_as(client, db, monkeypatch, FIXTURE_CUSTOMER)

    mock_chat = AsyncMock(side_effect=[tool_call_message("send_verification_code", {}), text_message("ok")])
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    resp = await client.post("/api/chat", json={"message": "send me a new code"})

    assert resp.json()["state"] == "verified"
    assert resp.json()["requires_code_modal"] is False
    row = await get_session_row(db, client)
    assert row.code_hash is None
    assert row.state == SessionState.verified


@pytest.mark.asyncio
async def test_unknown_tool_is_refused_and_logged(client: AsyncClient, monkeypatch, caplog):
    mock_chat = AsyncMock(side_effect=[tool_call_message("run_sql", {"query": "SELECT * FROM shipments"}), text_message("no")])
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    caplog.set_level(logging.INFO, logger="secureship.tools")

    resp = await client.post("/api/chat", json={"message": "hi"})

    assert resp.status_code == 200
    assert tool_results(mock_chat) == [{"error": "not_allowed"}]
    assert "tool DENIED name=<unknown> reason=unknown_tool state=anonymous" in caplog.text
    assert "run_sql" not in caplog.text and "SELECT" not in caplog.text


@pytest.mark.asyncio
async def test_non_dict_arguments_are_refused_without_error(client: AsyncClient, db: AsyncSession, monkeypatch):
    bad_call = {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "verify_identity", "arguments": "Testina"}}]}
    mock_chat = AsyncMock(side_effect=[bad_call, text_message("Could you give me your details?")])
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    resp = await client.post("/api/chat", json={"message": "where's my package?"})

    assert resp.status_code == 200
    assert tool_results(mock_chat)[0]["error"] == "invalid_arguments"
    row = await get_session_row(db, client)
    assert row.state == SessionState.anonymous


def test_require_verified_checks_state_not_only_customer_id():
    now = datetime.now(timezone.utc)
    # customer_id + verified_at set, but the session is not in the verified state (e.g. dropped back to awaiting_code)
    inconsistent = ChatSession(state=SessionState.awaiting_code, customer_id=uuid.uuid4(), verified_at=now, transcript=[])
    with pytest.raises(ToolDenied) as denied:
        require_verified(inconsistent)
    assert denied.value.reason == "not_verified"

    for missing in ({"customer_id": None, "verified_at": now}, {"customer_id": uuid.uuid4(), "verified_at": None}):
        with pytest.raises(ToolDenied):
            require_verified(ChatSession(state=SessionState.verified, transcript=[], **missing))

    require_verified(ChatSession(state=SessionState.verified, customer_id=uuid.uuid4(), verified_at=now, transcript=[]))
