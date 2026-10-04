from typing import Any


def tool_call_message(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
    }


def text_message(content: str) -> dict[str, Any]:
    return {"role": "assistant", "content": content}


async def get_session_row(db, client):
    """The ChatSession row behind the test client's session cookie."""
    from sqlalchemy import select

    from config import settings
    from models import ChatSession

    token = client.cookies.get(settings.session_cookie_name)
    result = await db.execute(select(ChatSession).where(ChatSession.session_token == token))
    return result.scalar_one()


async def verify_as(client, db, monkeypatch, identity: dict[str, Any]) -> None:
    """Take the client's session through the real flow to `verified` as `identity` (fake model, known code)."""
    from unittest.mock import AsyncMock

    from services.verification import generate_code, hash_code

    mock_chat = AsyncMock(
        side_effect=[
            tool_call_message("verify_identity", identity),
            tool_call_message("send_verification_code", {}),
            text_message("I've texted you a code."),
        ]
    )
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    resp = await client.post("/api/chat", json={"message": "where's my package?"})
    assert resp.json()["state"] == "awaiting_code"

    row = await get_session_row(db, client)
    code = generate_code()
    row.code_hash = hash_code(code)
    await db.commit()
    resp = await client.post("/api/verify", json={"code": code})
    assert resp.json()["state"] == "verified"


def tool_results(mock_chat) -> list[dict[str, Any]]:
    """The tool results the backend fed back to the (fake) model, in order."""
    import json

    history = mock_chat.await_args_list[-1].args[1]
    return [json.loads(m["content"]) for m in history if m["role"] == "tool"]


def history_text(mock_chat) -> str:
    """Everything the (fake) model was sent across all calls of this turn, as one string."""
    import json

    return json.dumps([call.args for call in mock_chat.await_args_list], default=str)
