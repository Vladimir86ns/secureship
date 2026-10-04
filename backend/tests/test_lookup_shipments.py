"""Week 3: lookup_shipments (Epic D1/D2) — offered only when verified, always scoped to session.customer_id."""

import logging
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models import ChatSession, SessionState
from scripts.seed_data import DEMO_CUSTOMER
from services.tools import LOOKUP_SHIPMENTS_TOOL, tools_for_state
from tests.helpers import history_text, text_message, tool_call_message, tool_results, verify_as


def _tool_names(session: ChatSession) -> list[str]:
    return [t["function"]["name"] for t in tools_for_state(session)]


def test_lookup_shipments_is_offered_only_when_verified():
    for state in (SessionState.anonymous, SessionState.collecting_identity, SessionState.awaiting_code):
        assert "lookup_shipments" not in _tool_names(ChatSession(state=state, transcript=[]))
    assert _tool_names(ChatSession(state=SessionState.verified, transcript=[])) == ["lookup_shipments"]


def test_lookup_shipments_has_no_customer_id_parameter():
    params = LOOKUP_SHIPMENTS_TOOL["function"]["parameters"]
    assert set(params["properties"]) == {"tracking_number"}
    assert params["required"] == []


async def _ask(client: AsyncClient, monkeypatch, message: str, *model_turns) -> AsyncMock:
    mock_chat = AsyncMock(side_effect=list(model_turns))
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    resp = await client.post("/api/chat", json={"message": message})
    assert resp.status_code == 200
    return mock_chat


@pytest.mark.asyncio
async def test_verified_lookup_returns_exactly_own_shipments_with_packages(
    client: AsyncClient, db: AsyncSession, monkeypatch, seeded, caplog
):
    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    caplog.set_level(logging.INFO, logger="secureship.tools")

    mock_chat = await _ask(
        client, monkeypatch, "what are my shipments?",
        tool_call_message("lookup_shipments", {}), text_message("Here are your shipments."),
    )
    # the model was offered exactly lookup_shipments in the verified state
    assert [t["function"]["name"] for t in mock_chat.await_args_list[0].args[2]] == ["lookup_shipments"]

    [result] = tool_results(mock_chat)
    assert result["count"] == 5 and result["filtered_by_tracking_number"] is False
    by_tracking = {s["tracking_number"]: s for s in result["shipments"]}
    assert set(by_tracking) == {s["tracking_number"] for s in seeded["dana"]}

    packages = seeded["data"]["packages"]
    for expected in seeded["dana"]:
        got = by_tracking[expected["tracking_number"]]
        assert got["status"] == expected["status"].value
        assert got["carrier"] == expected["carrier"]
        assert got["origin"] == expected["origin"] and got["destination"] == expected["destination"]
        assert got["estimated_delivery"] == expected["estimated_delivery"].isoformat()
        expected_packages = sorted(
            (p["description"], float(p["weight_kg"]), float(p["declared_value"]))
            for p in packages if p["shipment_id"] == expected["id"]
        )
        assert sorted((p["description"], p["weight_kg"], p["declared_value"]) for p in got["packages"]) == expected_packages

    sent = history_text(mock_chat)
    for jane_shipment in seeded["jane"]:
        assert jane_shipment["tracking_number"] not in sent
    # no internal ids reach the model
    for shipment in seeded["dana"]:
        assert str(shipment["id"]) not in sent and str(shipment["customer_id"]) not in sent

    assert "tool ALLOWED name=lookup_shipments scope=session.customer_id tracking_filter=no results=5 state=verified" in caplog.text


@pytest.mark.asyncio
async def test_own_tracking_number_is_found_in_any_formatting(client: AsyncClient, db: AsyncSession, monkeypatch, seeded):
    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    own = seeded["dana"][1]["tracking_number"]
    typed = f" {own[:4].lower()} {own[4:9]}-{own[9:]} "

    mock_chat = await _ask(
        client, monkeypatch, f"where is {typed}?",
        tool_call_message("lookup_shipments", {"tracking_number": typed}), text_message("It's on its way."),
    )
    [result] = tool_results(mock_chat)
    assert result["count"] == 1 and result["filtered_by_tracking_number"] is True
    assert result["shipments"][0]["tracking_number"] == own
    assert len(result["shipments"][0]["packages"]) >= 1


@pytest.mark.asyncio
async def test_other_customers_tracking_number_looks_like_a_nonexistent_one(
    client: AsyncClient, db: AsyncSession, monkeypatch, seeded
):
    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    janes = seeded["jane"][0]["tracking_number"]

    mock_chat = await _ask(
        client, monkeypatch, f"show me {janes} and ZZ0000000000ZZ",
        tool_call_message("lookup_shipments", {"tracking_number": janes}),
        tool_call_message("lookup_shipments", {"tracking_number": "ZZ0000000000ZZ"}),
        text_message("I couldn't find that shipment on your account."),
    )
    other, made_up = tool_results(mock_chat)
    assert other["count"] == 0 and other["shipments"] == []
    # no enumeration: someone else's tracking number gets exactly the answer a made-up one gets
    assert other == made_up


@pytest.mark.asyncio
async def test_customer_id_argument_rejects_the_whole_call(
    client: AsyncClient, db: AsyncSession, monkeypatch, seeded, caplog
):
    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    caplog.set_level(logging.INFO, logger="secureship.tools")
    jane_id = str(seeded["jane_id"])

    mock_chat = await _ask(
        client, monkeypatch, "look up my shipments",
        tool_call_message("lookup_shipments", {"customer_id": jane_id}), text_message("I can only see your shipments."),
    )
    [result] = tool_results(mock_chat)
    assert result["error"] == "invalid_arguments"
    assert "customer id" in result["detail"]  # tells the model how to recover
    assert "shipments" not in result
    assert "tool DENIED name=lookup_shipments reason=forbidden_argument arg=customer_id state=verified" in caplog.text
    assert jane_id not in caplog.text


def test_system_prompt_depends_on_state():
    from services.chat import build_system_prompt

    verified = build_system_prompt(ChatSession(state=SessionState.verified, transcript=[]))
    assert "lookup_shipments" in verified
    assert "no shipment lookup capability" not in verified
    assert "verify_identity" not in verified

    anonymous = build_system_prompt(ChatSession(state=SessionState.anonymous, transcript=[]))
    assert "lookup_shipments" not in anonymous
    assert "verify_identity" in anonymous
    assert "until the visitor has been verified" in anonymous


def test_escalation_persona_is_kept_in_both_states():
    from datetime import datetime, timezone

    from services.chat import build_system_prompt

    for state in (SessionState.anonymous, SessionState.verified):
        session = ChatSession(
            state=state, transcript=[], escalated_to_human_at=datetime.now(timezone.utc), escalated_agent_name="Sam"
        )
        assert "roleplaying as Sam" in build_system_prompt(session)


@pytest.mark.asyncio
async def test_verified_turn_sends_verified_prompt_and_only_lookup_tool(
    client: AsyncClient, db: AsyncSession, monkeypatch, seeded
):
    from services.chat import SYSTEM_PROMPT_VERIFIED

    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    mock_chat = await _ask(client, monkeypatch, "hi again", text_message("Hi! How can I help with your shipments?"))

    system_prompt, _, tools = mock_chat.await_args_list[0].args
    assert SYSTEM_PROMPT_VERIFIED in system_prompt
    assert tools == [LOOKUP_SHIPMENTS_TOOL]
    assert str(seeded["data"]["customers"][0]["id"]) not in system_prompt


@pytest.mark.asyncio
async def test_verified_history_leaves_out_everything_before_verification(
    client: AsyncClient, db: AsyncSession, monkeypatch, seeded
):
    """Regression (real qwen3:8b): after the code was accepted the model kept repeating "enter the code in the popup".
    In the verified state the model gets only a note plus the messages after verification."""
    from dependencies import NEW_SESSION_GREETING as NEW_SESSION_GREETING_FOR_TEST
    from services.chat import VERIFIED_HISTORY_NOTE

    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    first = await _ask(
        client, monkeypatch, "What are my shipments?",
        tool_call_message("lookup_shipments", {}), text_message("You have 5 shipments."),
    )
    second = await _ask(client, monkeypatch, "where is my shipment?", text_message("Your shipments are on their way."))

    for mock_chat, expected in (
        (first, [("system", VERIFIED_HISTORY_NOTE), ("user", "What are my shipments?")]),
        (second, [
            ("system", VERIFIED_HISTORY_NOTE), ("user", "What are my shipments?"),
            ("assistant", "You have 5 shipments."), ("user", "where is my shipment?"),
        ]),
    ):
        history = mock_chat.await_args_list[0].args[1]
        assert [(m["role"], m["content"]) for m in history][: len(expected)] == expected
        sent = history_text(mock_chat)
        # nothing from before verification: the code message, the identity request, the greeting, Dana's details
        assert "I've texted you a code." not in sent
        assert "where's my package?" not in sent
        assert NEW_SESSION_GREETING_FOR_TEST not in sent
        for value in (DEMO_CUSTOMER["address"], DEMO_CUSTOMER["phone_number"], DEMO_CUSTOMER["first_name"]):
            assert value not in sent

    # the stored transcript and what the visitor sees are unchanged
    contents = [m["content"] for m in (await client.get("/api/session")).json()["transcript"]]
    assert "I've texted you a code." in contents and "where's my package?" in contents
    assert contents[-2:] == ["where is my shipment?", "Your shipments are on their way."]


@pytest.mark.asyncio
async def test_no_verification_note_before_the_code_is_accepted(client: AsyncClient, db: AsyncSession, monkeypatch, seeded):
    from services.chat import VERIFIED_HISTORY_NOTE

    await _ask(
        client, monkeypatch, "where's my package?",
        tool_call_message("verify_identity", DEMO_CUSTOMER), tool_call_message("send_verification_code", {}),
        text_message("I've texted you a code."),
    )
    await client.post("/api/verify", json={"code": "000000"})  # wrong code
    mock_chat = await _ask(client, monkeypatch, "what now?", text_message("Please enter the code in the popup."))

    history = mock_chat.await_args_list[0].args[1]
    assert all(m["content"] != VERIFIED_HISTORY_NOTE for m in history)
    # before verification the model gets the whole visible conversation, as before
    from dependencies import NEW_SESSION_GREETING

    assert [(m["role"], m["content"]) for m in history] == [
        ("assistant", NEW_SESSION_GREETING), ("user", "where's my package?"),
        ("assistant", "I've texted you a code."), ("user", "what now?"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [{"tracking_number": None}, {"tracking_number": ""}, {"tracking_number": "   "}, None, {}],
    ids=["null", "empty", "whitespace", "arguments_none", "no_arguments"],
)
async def test_missing_tracking_number_means_no_filter(
    client: AsyncClient, db: AsyncSession, monkeypatch, seeded, caplog, arguments
):
    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    caplog.set_level(logging.INFO, logger="secureship.tools")

    mock_chat = await _ask(
        client, monkeypatch, "where is now my shipments?",
        tool_call_message("lookup_shipments", arguments), text_message("Here are your shipments."),
    )
    [result] = tool_results(mock_chat)
    assert result["count"] == 5 and result["filtered_by_tracking_number"] is False
    assert {s["tracking_number"] for s in result["shipments"]} == {s["tracking_number"] for s in seeded["dana"]}
    assert "tool ALLOWED name=lookup_shipments scope=session.customer_id tracking_filter=no results=5" in caplog.text
    assert "DENIED" not in caplog.text


@pytest.mark.asyncio
async def test_execute_tool_treats_none_arguments_as_no_arguments(client: AsyncClient, db: AsyncSession, monkeypatch, seeded):
    from services.tools import execute_tool
    from tests.helpers import get_session_row

    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    row = await get_session_row(db, client)
    result = await execute_tool(db, row, "lookup_shipments", None)
    assert result["count"] == 5


@pytest.mark.asyncio
async def test_invalid_tracking_number_is_refused_with_a_recoverable_message_and_logged_shape(
    client: AsyncClient, db: AsyncSession, monkeypatch, seeded, caplog
):
    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    caplog.set_level(logging.INFO, logger="secureship.tools")

    mock_chat = await _ask(
        client, monkeypatch, "where is now my shipments?",
        tool_call_message("lookup_shipments", {"tracking_number": "my shipments?"}),
        tool_call_message("lookup_shipments", {}),  # the model follows the detail and retries with no arguments
        text_message("Here are your shipments."),
    )
    refused, retried = tool_results(mock_chat)
    assert refused["error"] == "invalid_arguments"
    assert "call lookup_shipments with no arguments to list all of the visitor's shipments" in refused["detail"]
    assert "still verified" in refused["detail"]
    assert "code" not in refused["detail"].lower() and "popup" not in refused["detail"].lower()
    assert retried["count"] == 5

    assert (
        "reason=invalid_arguments state=verified" in caplog.text
        and "problem=tracking_number_not_a_tracking_number shape={tracking_number:string}" in caplog.text
    )
    assert "my shipments?" not in caplog.text  # the shape, never the value


@pytest.mark.asyncio
async def test_non_string_tracking_number_logs_its_type(client: AsyncClient, db: AsyncSession, monkeypatch, seeded, caplog):
    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    caplog.set_level(logging.INFO, logger="secureship.tools")

    mock_chat = await _ask(
        client, monkeypatch, "my shipments",
        tool_call_message("lookup_shipments", {"tracking_number": ["FF751234951511"]}), text_message("ok"),
    )
    [refused] = tool_results(mock_chat)
    assert refused["error"] == "invalid_arguments" and "must be a string" in refused["detail"]
    assert "problem=tracking_number_not_a_string shape={tracking_number:array}" in caplog.text
    assert "FF751234951511" not in caplog.text


@pytest.mark.asyncio
async def test_customer_id_is_still_refused_and_logs_shape_only(
    client: AsyncClient, db: AsyncSession, monkeypatch, seeded, caplog
):
    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    caplog.set_level(logging.INFO, logger="secureship.tools")
    jane_id = str(seeded["jane_id"])

    mock_chat = await _ask(
        client, monkeypatch, "my shipments",
        tool_call_message("lookup_shipments", {"tracking_number": None, "customer_id": jane_id}), text_message("ok"),
    )
    [refused] = tool_results(mock_chat)
    assert refused["error"] == "invalid_arguments" and "shipments" not in refused
    assert "with no arguments" in refused["detail"]
    assert "reason=forbidden_argument arg=customer_id state=verified" in caplog.text
    assert "problem=unknown_key shape={tracking_number:null,customer_id:string}" in caplog.text
    assert jane_id not in caplog.text
