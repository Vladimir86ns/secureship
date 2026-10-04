"""Tool layer (Epic F): the tool definitions the model may see, and their execution.

Every tool call the model makes goes through execute_tool -> authorize_tool_call, the single
enforcement point (Epic F3). The model's output is never trusted: a tool runs only if the backend
would offer it in the session's current state, and a shipment tool additionally only if
require_verified passes.
"""

import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import ChatSession, SessionState, Shipment
from services.customer_match import match_customer
from services.transcript import transition_state, visible_entries
from services.verification import dispatch_verification_code

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

LOOKUP_SHIPMENTS_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_shipments",
        "description": (
            "Look up the verified visitor's OWN shipments and their packages. It can only ever return shipments "
            "that belong to the visitor verified in this chat; it cannot look up anyone else. Call it for any "
            "question about the visitor's shipments, orders, packages, deliveries or tracking. Optionally narrow "
            "to one tracking number."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tracking_number": {
                    "type": "string",
                    "description": (
                        "Optional. Only this tracking number, if the visitor gave one. "
                        "Omit it to list all of the visitor's shipments."
                    ),
                },
            },
            "required": [],
        },
    },
}


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


async def _tool_send_verification_code(
    db: AsyncSession, session: ChatSession, arguments: dict[str, Any]
) -> dict[str, Any]:
    return dispatch_verification_code(session)


_LOG_TRACKING_FILTER = "_log_tracking_filter"  # for the log line only; removed before the model sees the result
_TRACKING_SEPARATORS_RE = re.compile(r"[\s-]+")
_TRACKING_RE = re.compile(r"^[A-Z0-9]{1,40}$")


def _normalize_tracking(value: Any) -> str | None:
    """trim + upper + no spaces/dashes. None = no filter (also for null, "" and whitespace only).
    Raises ToolDenied on anything that isn't a tracking number."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolDenied("invalid_arguments", problem="tracking_number_not_a_string")
    normalized = _TRACKING_SEPARATORS_RE.sub("", value).upper()
    if not normalized:
        return None
    if not _TRACKING_RE.match(normalized):
        raise ToolDenied("invalid_arguments", problem="tracking_number_not_a_tracking_number")
    return normalized


def _tracking_in_conversation(session: ChatSession, tracking_number: str) -> bool:
    """Did this tracking number (same normalization) appear in a visible message of THIS session — typed by
    the visitor or in an earlier assistant reply? A number only the model came up with does not count."""
    return any(
        tracking_number in _TRACKING_SEPARATORS_RE.sub("", str(entry.get("content") or "")).upper()
        for entry in visible_entries(session.transcript)
    )


def _validate_lookup_arguments(arguments: dict[str, Any]) -> None:
    _normalize_tracking(arguments.get("tracking_number"))


async def _lookup_shipments(db: AsyncSession, customer_id: uuid.UUID, tracking_number: str | None) -> list[Shipment]:
    """The only shipment query reachable from the model. ALWAYS filtered by the given customer_id (Epic D2)."""
    stmt = (
        select(Shipment)
        .where(Shipment.customer_id == customer_id)
        .options(selectinload(Shipment.packages))
        .order_by(Shipment.last_update.desc())
    )
    if tracking_number:
        stmt = stmt.where(Shipment.tracking_number == tracking_number)
    return list((await db.execute(stmt)).scalars().all())


def _shipment_for_model(shipment: Shipment) -> dict[str, Any]:
    """Section 4.4 fields only — no internal ids, nothing about the customer."""
    return {
        "tracking_number": shipment.tracking_number,
        "status": shipment.status.value,
        "carrier": shipment.carrier,
        "origin": shipment.origin,
        "destination": shipment.destination,
        "estimated_delivery": shipment.estimated_delivery.isoformat(),
        "last_update": shipment.last_update.isoformat(),
        "packages": [
            {
                "description": p.description,
                "weight_kg": float(p.weight_kg),
                "declared_value": float(p.declared_value),
            }
            for p in shipment.packages
        ],
    }


async def _tool_lookup_shipments(
    db: AsyncSession, session: ChatSession, arguments: dict[str, Any]
) -> dict[str, Any]:
    # Epic F / 6.3: the customer is ALWAYS session.customer_id (set only by check_verification_code),
    # never an argument — authorize_tool_call already refused any argument other than tracking_number.
    tracking_number = _normalize_tracking(arguments.get("tracking_number"))
    tracking_filter = "no"
    if tracking_number is not None:
        if _tracking_in_conversation(session, tracking_number):
            tracking_filter = "yes"
        else:
            # The model made the number up (seen with qwen3:8b): ignore it and list all of the
            # visitor's shipments instead of a misleading "not found". Still scoped to this customer.
            tracking_number, tracking_filter = None, "ignored"
    shipments = await _lookup_shipments(db, customer_id=session.customer_id, tracking_number=tracking_number)
    return {
        "today": datetime.now(timezone.utc).date().isoformat(),
        "count": len(shipments),
        "filtered_by_tracking_number": tracking_number is not None,
        "shipments": [_shipment_for_model(s) for s in shipments],
        _LOG_TRACKING_FILTER: tracking_filter,
    }


logger = logging.getLogger("secureship.tools")

_IDENTITY_STATES = (SessionState.anonymous, SessionState.collecting_identity)


class ToolDenied(Exception):
    def __init__(self, reason: str, arg: str | None = None, problem: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.arg = arg  # only the NAME of an offending argument, never its value
        self.problem = problem  # which argument check failed (a fixed code, never a value)


@dataclass(frozen=True)
class ToolSpec:
    definition: dict[str, Any]
    handler: Callable[[AsyncSession, ChatSession, dict[str, Any]], Awaitable[dict[str, Any]]]
    is_offered: Callable[[ChatSession], bool]
    kind: str  # "identity" | "shipments"
    allowed_args: frozenset[str] | None = None  # None = not checked (identity tools validate their own fields)
    # returned to the model on a rejected call, so it can recover — keyed by ToolDenied.problem, "default" otherwise
    invalid_args_detail: dict[str, str] | None = None
    validate: Callable[[dict[str, Any]], None] | None = None  # raises ToolDenied("invalid_arguments")

    @property
    def name(self) -> str:
        return self.definition["function"]["name"]


TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec(
            definition=VERIFY_IDENTITY_TOOL,
            handler=_tool_verify_identity,
            is_offered=lambda s: s.state in _IDENTITY_STATES,
            kind="identity",
        ),
        ToolSpec(
            definition=SEND_VERIFICATION_CODE_TOOL,
            handler=_tool_send_verification_code,
            is_offered=lambda s: s.state in _IDENTITY_STATES and s.pending_customer_id is not None,
            kind="identity",
        ),
        ToolSpec(
            definition=LOOKUP_SHIPMENTS_TOOL,
            handler=_tool_lookup_shipments,
            is_offered=lambda s: s.state == SessionState.verified,
            kind="shipments",
            allowed_args=frozenset({"tracking_number"}),
            invalid_args_detail={
                "unknown_key": (
                    "lookup_shipments accepts only an optional tracking_number. It has no customer id or any other "
                    "parameter, and it only ever returns the visitor's own shipments. The visitor is still verified — "
                    "call lookup_shipments with no arguments to list all of the visitor's shipments."
                ),
                "tracking_number_not_a_string": (
                    "tracking_number must be a string. The visitor is still verified — call lookup_shipments with no "
                    "arguments to list all of the visitor's shipments."
                ),
                "tracking_number_not_a_tracking_number": (
                    "tracking_number must be a tracking number the visitor actually gave (letters and digits only), "
                    "not a description. The visitor is still verified — call lookup_shipments with no arguments to "
                    "list all of the visitor's shipments."
                ),
                "default": (
                    "The arguments must be a JSON object. The visitor is still verified — call lookup_shipments with "
                    "no arguments to list all of the visitor's shipments."
                ),
            },
            validate=_validate_lookup_arguments,
        ),
    )
}


def tools_for_state(session: ChatSession) -> list[dict[str, Any]]:
    """The backend decides which tools are even visible to the model this turn."""
    return [spec.definition for spec in TOOLS.values() if spec.is_offered(session)]


def require_verified(session: ChatSession) -> None:
    """Epic F3: the ONLY place "verified" is decided for shipment tools.

    All three must hold: the session is in the verified state, the verified customer is set
    (only check_verification_code sets it), and the verification time is recorded.
    """
    if session.state != SessionState.verified or session.customer_id is None or session.verified_at is None:
        raise ToolDenied("not_verified")


def authorize_tool_call(session: ChatSession, name: str, arguments: Any) -> ToolSpec:
    """Epic F3 — the single enforcement point, run before EVERY tool. Raises ToolDenied."""
    spec = _spec_for(name)
    if spec is None:
        raise ToolDenied("unknown_tool")
    if not spec.is_offered(session):
        raise ToolDenied("not_offered")
    if spec.kind == "shipments":
        require_verified(session)
    if not isinstance(arguments, dict):
        raise ToolDenied("invalid_arguments", problem="not_an_object")
    if spec.allowed_args is not None:
        for key in arguments:
            if key not in spec.allowed_args:
                raise ToolDenied("forbidden_argument", arg=_safe_arg_name(key), problem="unknown_key")
    if spec.validate is not None:
        spec.validate(arguments)
    return spec


def _spec_for(name: Any) -> ToolSpec | None:
    return TOOLS.get(name) if isinstance(name, str) else None


def _safe_arg_name(key: Any) -> str:
    # Only an argument's NAME is ever logged; keep it short and printable.
    return re.sub(r"[^A-Za-z0-9_]", "?", str(key))[:40]


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "other"


def _args_shape(arguments: Any) -> str:
    """The SHAPE of what the model sent — key names and JSON types, never the values. E.g. {tracking_number:null}."""
    if isinstance(arguments, dict):
        return ("{" + ",".join(f"{_safe_arg_name(k)}:{_json_type(v)}" for k, v in arguments.items()) + "}")[:200]
    return _json_type(arguments)


def _session_ref(session: ChatSession) -> str:
    # The row id, never session_token (that is the secret cookie value).
    return str(session.id)[:8] if session.id else "-"


def _result_for_denied(spec: ToolSpec | None, denied: ToolDenied) -> dict[str, Any]:
    """What the model gets back. Neutral: nothing says whether any shipment or customer exists (Epic A3)."""
    if spec is not None and denied.reason in ("forbidden_argument", "invalid_arguments"):
        details = spec.invalid_args_detail or {}
        return {"error": "invalid_arguments", "detail": details.get(denied.problem or "", details.get("default", ""))}
    if spec is not None and spec.kind == "shipments" and denied.reason in ("not_offered", "not_verified"):
        return {"error": "verification_required"}
    return {"error": "not_allowed"}


async def execute_tool(
    db: AsyncSession, session: ChatSession, name: str, arguments: Any
) -> dict[str, Any]:
    if arguments is None:
        arguments = {}  # "no arguments" — the same as {}
    try:
        spec = authorize_tool_call(session, name, arguments)
    except ToolDenied as denied:
        arg = f" arg={denied.arg}" if denied.arg else ""
        extra = ""
        if denied.reason in ("forbidden_argument", "invalid_arguments"):
            extra = f" problem={denied.problem or '-'} shape={_args_shape(arguments)}"
        logger.warning(
            "tool DENIED name=%s reason=%s%s state=%s session=%s%s",
            name if _spec_for(name) else "<unknown>", denied.reason, arg, session.state.value, _session_ref(session),
            extra,
        )
        return _result_for_denied(_spec_for(name), denied)

    state = session.state.value  # the state the decision was made in (an identity tool may move it on)
    result = await spec.handler(db, session, arguments)
    if spec.kind == "shipments":
        logger.info(
            "tool ALLOWED name=%s scope=session.customer_id tracking_filter=%s results=%s state=%s session=%s",
            name, result.pop(_LOG_TRACKING_FILTER, "no"), result.get("count"),
            state, _session_ref(session),
        )
    else:
        logger.info("tool ALLOWED name=%s state=%s session=%s", name, state, _session_ref(session))
    return result
