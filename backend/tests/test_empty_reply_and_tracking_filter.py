"""Manual-test fixes (qwen3:8b): an empty model reply is retried once, and lookup_shipments only filters
by a tracking number that actually appeared in this chat (a number the model made up is ignored)."""

import logging
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.seed_data import DEMO_CUSTOMER
from tests.helpers import history_text, text_message, tool_call_message, tool_results, verify_as


async def _ask(client: AsyncClient, monkeypatch, message: str, *model_turns):
    mock_chat = AsyncMock(side_effect=list(model_turns))
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    resp = await client.post("/api/chat", json={"message": message})
    assert resp.status_code == 200
    return mock_chat, resp.json()


def _last_reply(body: dict) -> str:
    return [m for m in body["messages"] if m["role"] == "assistant"][-1]["content"]


def _log(caplog, name: str) -> str:
    return "\n".join(r.getMessage() for r in caplog.records if r.name == name)


@pytest.fixture
def tools_log(caplog):
    caplog.set_level(logging.INFO, logger="secureship.tools")
    return caplog


# --- A) empty model reply -> one retry ---


@pytest.mark.asyncio
async def test_empty_reply_then_good_reply_reaches_the_visitor(client: AsyncClient, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="secureship.chat")
    mock_chat, body = await _ask(client, monkeypatch, "What are my shipments?", text_message(""), text_message("Hello!"))

    assert mock_chat.await_count == 2
    assert mock_chat.await_args_list[0].args == mock_chat.await_args_list[1].args  # the same call, repeated
    assert _last_reply(body) == "Hello!"
    assert "empty model reply, retried once retry_result=ok" in _log(caplog, "secureship.chat")


@pytest.mark.asyncio
async def test_two_empty_replies_give_the_fallback(client: AsyncClient, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="secureship.chat")
    mock_chat, body = await _ask(client, monkeypatch, "What are my shipments?", text_message(""), text_message("  "))

    assert mock_chat.await_count == 2
    assert _last_reply(body) == "Could you rephrase that?"
    assert "empty model reply, retried once retry_result=empty" in _log(caplog, "secureship.chat")


# --- B) tracking filter only for a number that appeared in the chat ---


@pytest.mark.asyncio
async def test_tracking_number_not_in_the_chat_is_ignored(
    client: AsyncClient, db: AsyncSession, monkeypatch, seeded, tools_log
):
    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)

    mock_chat, _ = await _ask(
        client, monkeypatch, "where is my shipment now",
        tool_call_message("lookup_shipments", {"tracking_number": "ZZ0000000000ZZ"}),
        text_message("Here are your shipments."),
    )
    [result] = tool_results(mock_chat)
    assert result["count"] == 5 and result["filtered_by_tracking_number"] is False
    assert {s["tracking_number"] for s in result["shipments"]} == {s["tracking_number"] for s in seeded["dana"]}
    assert "_log_tracking_filter" not in result  # log-only field never reaches the model
    assert "scope=session.customer_id tracking_filter=ignored results=5" in _log(tools_log, "secureship.tools")


@pytest.mark.asyncio
async def test_visitor_typed_own_tracking_number_with_spaces_filters(
    client: AsyncClient, db: AsyncSession, monkeypatch, seeded, tools_log
):
    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    own = seeded["dana"][2]["tracking_number"]
    spaced = " ".join(own[i:i + 4] for i in range(0, len(own), 4))

    mock_chat, _ = await _ask(
        client, monkeypatch, f"where is {spaced}?",
        tool_call_message("lookup_shipments", {"tracking_number": own}), text_message("It's on its way."),
    )
    [result] = tool_results(mock_chat)
    assert result["count"] == 1 and result["shipments"][0]["tracking_number"] == own
    assert "scope=session.customer_id tracking_filter=yes results=1" in _log(tools_log, "secureship.tools")


@pytest.mark.asyncio
async def test_tracking_number_from_an_earlier_assistant_reply_filters(
    client: AsyncClient, db: AsyncSession, monkeypatch, seeded
):
    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    own = seeded["dana"][0]["tracking_number"]
    await _ask(client, monkeypatch, "what are my shipments?", text_message(f"You have shipment {own}."))

    mock_chat, _ = await _ask(
        client, monkeypatch, "where is that one?",
        tool_call_message("lookup_shipments", {"tracking_number": own}), text_message("It's on its way."),
    )
    [result] = tool_results(mock_chat)
    assert result["count"] == 1 and result["shipments"][0]["tracking_number"] == own


@pytest.mark.asyncio
async def test_visitor_typed_other_customers_tracking_number_finds_nothing(
    client: AsyncClient, db: AsyncSession, monkeypatch, seeded, tools_log
):
    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    janes = seeded["jane"][0]["tracking_number"]

    mock_chat, body = await _ask(
        client, monkeypatch, f"Where is {janes}?",
        tool_call_message("lookup_shipments", {"tracking_number": janes}),
        text_message("I couldn't find that shipment on your account."),
    )
    [result] = tool_results(mock_chat)
    assert result["count"] == 0 and result["shipments"] == []
    # nothing of Jane's beyond the number the visitor typed themselves reaches the model or the visitor
    sent, shown = history_text(mock_chat), str(body)
    for s in seeded["jane"]:
        for value in (s["origin"], s["destination"], str(s["id"]), str(s["customer_id"])):
            assert value not in sent and value not in shown
    for s in seeded["jane"][1:]:
        assert s["tracking_number"] not in sent and s["tracking_number"] not in shown
    assert "scope=session.customer_id tracking_filter=yes results=0" in _log(tools_log, "secureship.tools")
