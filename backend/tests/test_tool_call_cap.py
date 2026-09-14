from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from config import settings
from tests.conftest import FIXTURE_CUSTOMER
from tests.helpers import tool_call_message


@pytest.mark.asyncio
async def test_tool_call_cap_falls_back_gracefully(client: AsyncClient, monkeypatch):
    # Every round proposes another tool call — never a final plain-text answer.
    runaway = tool_call_message("verify_identity", FIXTURE_CUSTOMER)
    mock_chat = AsyncMock(side_effect=[runaway] * (settings.tool_call_max_rounds + 2))
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    resp = await client.post("/api/chat", json={"message": "where's my package?"})
    assert resp.status_code == 200
    body = resp.json()

    assert mock_chat.await_count == settings.tool_call_max_rounds
    assert len(body["messages"]) == 1
    assert "try again" in body["messages"][0]["content"].lower()
