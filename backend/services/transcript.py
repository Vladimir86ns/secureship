from datetime import datetime, timezone

from models import ChatSession, SessionState


def append_message(session: ChatSession, role: str, content: str) -> None:
    """Append a user-facing entry (rendered by the frontend)."""
    entry = {"role": role, "content": content, "at": datetime.now(timezone.utc).isoformat()}
    session.transcript = [*session.transcript, entry]


def append_internal_event(session: ChatSession, role: str, content: str, event: str) -> None:
    """Append an audit-only entry — persisted for Section 4.6, filtered out of API responses."""
    entry = {
        "role": role,
        "content": content,
        "at": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    session.transcript = [*session.transcript, entry]


def visible_entries(transcript: list[dict]) -> list[dict]:
    return [entry for entry in transcript if entry.get("event") is None]


def transition_state(session: ChatSession, new_state: SessionState) -> None:
    old_state = session.state
    if old_state == new_state:
        return
    session.state = new_state
    append_internal_event(
        session,
        "system_event",
        f"{old_state.value} -> {new_state.value}",
        event="state_change",
    )
