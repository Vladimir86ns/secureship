import random
import re
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from models import ChatSession, Customer, SessionState
from services.transcript import append_message, transition_state

ESCALATION_RE = re.compile(
    r"\b(human|agent|representative|real person|speak to someone)\b", re.IGNORECASE
)
AGENT_NAMES = ["Alex", "Jordan", "Sam", "Taylor", "Morgan"]


def wants_human(message: str) -> bool:
    return bool(ESCALATION_RE.search(message))


async def run_escalation_sequence(db: AsyncSession, session: ChatSession) -> None:
    """Deterministic, canned hand-off ("theater") — never routed through the LLM.

    Reachable from any state. Plays out with `state = escalated_to_human`, then
    resumes whatever state the conversation had actually reached beforehand —
    escalation never touches customer_id/verified_at, so identity gating is
    unaffected either way.
    """
    prior_state = session.state
    transition_state(session, SessionState.escalated_to_human)

    append_message(session, "assistant", "Sure, let me connect you with someone from our team.")
    append_message(session, "system_event", "Connecting you to a human agent…")

    name = random.choice(AGENT_NAMES)
    session.escalated_agent_name = name
    append_message(session, "system_event", f"{name} has joined the chat.")

    first_name = session.pending_first_name
    if not first_name and session.customer_id:
        customer = await db.get(Customer, session.customer_id)
        first_name = customer.first_name if customer else None

    greeting = f"Hi{' ' + first_name if first_name else ''}, this is {name} — how can I help?"
    append_message(session, "assistant", greeting)

    if session.escalated_to_human_at is None:
        session.escalated_to_human_at = datetime.now(timezone.utc)

    transition_state(session, prior_state)
