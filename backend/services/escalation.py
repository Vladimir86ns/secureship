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


# Section 6.2b, in this order (the frontend reveals them one after another and changes the window color at "color_shift").
ESCALATION_STEPS = ("acknowledging", "color_shift", "human_joined", "reading_up", "greeting")


async def run_escalation_sequence(db: AsyncSession, session: ChatSession) -> None:
    """Deterministic, canned hand-off ("theater") — never routed through the LLM.

    Reachable from any state. Plays out with `state = escalated_to_human`, then
    resumes whatever state the conversation had actually reached beforehand —
    escalation never touches customer_id/verified_at, so identity gating is
    unaffected either way.

    Section 6.2b: Acknowledging -> ColorShift -> HumanJoined -> ReadingUp -> Greeting.
    """
    prior_state = session.state
    transition_state(session, SessionState.escalated_to_human)

    append_message(session, "assistant", "Thank you for your patience — let me connect you with someone from our team.",
                   escalation_step="acknowledging")
    # the chat window changes color when this message is shown (frontend)
    append_message(session, "system_event", "Connecting you to a human agent…", escalation_step="color_shift")

    name = random.choice(AGENT_NAMES)
    session.escalated_agent_name = name
    append_message(session, "system_event", f"{name} has joined the chat.", escalation_step="human_joined")
    append_message(session, "assistant", f"Hello, my name is {name}, let me just read through the chat...", escalation_step="reading_up")

    first_name = session.pending_first_name
    if not first_name and session.customer_id:
        customer = await db.get(Customer, session.customer_id)
        first_name = customer.first_name if customer else None

    greeting = f"Hey{' ' + first_name if first_name else ''}, I'm up to speed — how can I help?"
    append_message(session, "assistant", greeting, escalation_step="greeting")

    if session.escalated_to_human_at is None:
        session.escalated_to_human_at = datetime.now(timezone.utc)

    transition_state(session, prior_state)
