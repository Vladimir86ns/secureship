from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import ChatSession
from tests.helpers import text_message


@pytest.mark.asyncio
async def test_two_turns_both_persist_and_second_call_includes_first_as_history(
    client: AsyncClient, db: AsyncSession, monkeypatch
):
    mock_chat = AsyncMock(side_effect=[text_message("Hi there!"), text_message("Sure, anything else?")])
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)

    await client.post("/api/chat", json={"message": "hello"})
    await client.post("/api/chat", json={"message": "thanks"})

    token = client.cookies.get(settings.session_cookie_name)
    result = await db.execute(select(ChatSession).where(ChatSession.session_token == token))
    row = result.scalar_one()

    contents = [e["content"] for e in row.transcript]
    assert "hello" in contents
    assert "thanks" in contents
    assert "Hi there!" in contents
    assert "Sure, anything else?" in contents

    # Second call's history (2nd positional arg to chat_completion) includes the first turn.
    second_call_history = mock_chat.await_args_list[1].args[1]
    history_contents = [m["content"] for m in second_call_history]
    assert "hello" in history_contents
    assert "Hi there!" in history_contents
