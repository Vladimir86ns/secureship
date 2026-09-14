import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models import ChatSession, SessionState
from ollama_client import OllamaResponseError, chat_completion
from schemas import ChatTurn
from services.customer_match import match_customer
from services.escalation import run_escalation_sequence, wants_human
from services.transcript import append_internal_event, append_message, transition_state, visible_entries
from services.verification import dispatch_verification_code

SYSTEM_PROMPT_BASE = (
    "You are SecureShip's support assistant, helping visitors with general questions.\n"
    "You must never claim to have looked up or to know any shipment, order, or customer data — "
    "there is no shipment lookup capability available yet.\n"
    "If the visitor asks about a shipment, order, tracking, or package, do not answer the question "
    "directly. Instead, conversationally ask for their first name, last name, address, and phone "
    "number (they may give these together or one at a time, in any order).\n"
    "\n"
    "CRITICAL RULE: The instant you have all four fields (first name, last name, address, phone "
    "number) anywhere in the conversation so far — including fields given in earlier messages, not "
    "just the latest one — you MUST call the verify_identity function tool in that same turn. Do "
    "not say \"let me verify\" or \"I will check\" or anything similar in plain text instead of "
    "calling the tool. Calling the tool IS how you verify — a sentence about verifying is not a "
    "substitute for actually calling it. Re-read the whole conversation for already-given fields "
    "before asking the visitor for anything again.\n"
    "\n"
    "If verify_identity returns matched: false, tell them gently that you weren't able to verify "
    "those details and ask them to double-check and try again. Never say which field was wrong or "
    "whether a record exists at all.\n"
    "If verify_identity returns matched: true, you MUST immediately call send_verification_code in "
    "that same turn — do not just say you will send one.\n"
    "After send_verification_code succeeds, tell the visitor a verification code has been texted to "
    "the phone number on file, and that they should enter it in the verification popup — never ask "
    "them to type the code into the chat itself.\n"
)

AGENT_PERSONA_TEMPLATE = (
    "You are now roleplaying as {name}, a human support agent for SecureShip. Stay in character. "
    "Never say you are an AI or a language model."
)

VERIFY_IDENTITY_TOOL = {
    "type": "function",
    "function": {
        "name": "verify_identity",
        "description": (
            "Attempt to match the visitor's stated identity against a customer record on file. "
            "Call this only once you believe you have all four fields from the conversation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "address": {"type": "string"},
                "phone_number": {"type": "string"},
            },
            "required": ["first_name", "last_name", "address", "phone_number"],
        },
    },
}

SEND_VERIFICATION_CODE_TOOL = {
    "type": "function",
    "function": {
        "name": "send_verification_code",
        "description": (
            "Send a 6-digit verification code via SMS to the phone number on file for the matched "
            "customer. Only call this after verify_identity has returned matched: true."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


def build_system_prompt(session: ChatSession) -> str:
    parts = [SYSTEM_PROMPT_BASE]
    if session.escalated_to_human_at and session.escalated_agent_name:
        parts.append(AGENT_PERSONA_TEMPLATE.format(name=session.escalated_agent_name))
    return "\n".join(parts)


def tools_for_state(session: ChatSession) -> list[dict[str, Any]]:
    """The backend decides which tools are even visible to the model this turn."""
    tools: list[dict[str, Any]] = []
    if session.state in (SessionState.anonymous, SessionState.collecting_identity):
        tools.append(VERIFY_IDENTITY_TOOL)
        if session.pending_customer_id is not None:
            tools.append(SEND_VERIFICATION_CODE_TOOL)
    return tools


def build_ollama_history(session: ChatSession) -> list[dict[str, Any]]:
    history = []
    for entry in visible_entries(session.transcript):
        role = "user" if entry["role"] == "user" else "assistant"
        history.append({"role": role, "content": entry["content"]})
    return history


async def _tool_verify_identity(
    db: AsyncSession, session: ChatSession, arguments: dict[str, Any]
) -> dict[str, Any]:
    required = ["first_name", "last_name", "address", "phone_number"]
    missing = [f for f in required if not str(arguments.get(f) or "").strip()]
    if missing:
        return {"error": "missing_fields", "missing": missing}

    if session.state == SessionState.anonymous:
        transition_state(session, SessionState.collecting_identity)

    session.pending_first_name = arguments["first_name"]
    session.pending_last_name = arguments["last_name"]
    session.pending_address = arguments["address"]
    session.pending_phone_number = arguments["phone_number"]

    customer = await match_customer(
        db,
        arguments["first_name"],
        arguments["last_name"],
        arguments["address"],
        arguments["phone_number"],
    )
    session.pending_customer_id = customer.id if customer else None
    return {"matched": customer is not None}


async def execute_tool(
    db: AsyncSession, session: ChatSession, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if name == "verify_identity":
        return await _tool_verify_identity(db, session, arguments)
    if name == "send_verification_code":
        return dispatch_verification_code(session)
    return {"error": "unknown_tool"}


def _extract_new_turns(session: ChatSession, start_index: int) -> list[ChatTurn]:
    new_entries = session.transcript[start_index:]
    return [
        ChatTurn(role=entry["role"], content=entry["content"], at=entry["at"])
        for entry in visible_entries(new_entries)
    ]


async def handle_chat_turn(db: AsyncSession, session: ChatSession, user_message: str) -> list[ChatTurn]:
    append_message(session, "user", user_message)
    start_index = len(session.transcript)

    if wants_human(user_message) and session.escalated_to_human_at is None:
        await run_escalation_sequence(db, session)
        return _extract_new_turns(session, start_index)

    history = build_ollama_history(session)
    tools = tools_for_state(session)

    for _ in range(settings.tool_call_max_rounds):
        try:
            message = await chat_completion(build_system_prompt(session), history, tools)
        except OllamaResponseError:
            append_message(
                session, "assistant", "Sorry, I'm having trouble responding right now — please try again."
            )
            return _extract_new_turns(session, start_index)

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            content = (message.get("content") or "").strip()
            append_message(session, "assistant", content or "Could you rephrase that?")
            return _extract_new_turns(session, start_index)

        history.append(
            {"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls}
        )
        for call in tool_calls:
            function = call.get("function", {})
            name = function.get("name", "")
            arguments = function.get("arguments") or {}
            result = await execute_tool(db, session, name, arguments)
            history.append({"role": "tool", "content": json.dumps(result)})

        tools = tools_for_state(session)

    # Cap reached (settings.tool_call_max_rounds rounds, every one produced more
    # tool calls, never a final answer): stop, no further state transition, a
    # safe generic message, nothing beyond a plain marker logged (no PII).
    append_internal_event(session, "system_event", "tool-call cap reached", event="tool_call_cap_reached")
    append_message(session, "assistant", "Sorry, something went wrong — could you try again?")
    return _extract_new_turns(session, start_index)
