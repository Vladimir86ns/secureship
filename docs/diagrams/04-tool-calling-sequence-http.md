# 6.3 Tool-calling sequence over HTTP (the gating enforcement point)

Regenerated against the implementation (Week 5). This is the transport the project uses
(HTTP request/response, no WebSocket — see [05](05-tool-calling-sequence-websocket.md)).

Differences from the starting diagram: the routes are `/api/chat` and `/api/verify`; the session comes from an httpOnly
cookie, not a `session_id` field; there is no `request_identity_info` tool (the model asks in plain text); identity uses
two separate tools (`verify_identity`, then `send_verification_code`); the code check is a backend service, not a tool;
`lookup_shipments` has **no** customer argument at all.

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend (React)
    participant BE as Backend (POST /api/chat)
    participant LLM as Ollama (qwen3:8b)
    participant Tools as Tool layer (services/tools.py)
    participant DB as Postgres

    User->>FE: Where is my package?
    FE->>BE: POST /api/chat {message} + session cookie
    BE->>DB: load chat_sessions row by cookie (state = anonymous)
    BE->>LLM: unverified system prompt + history + tools for the state
    LLM-->>BE: text asking for name, address and phone
    BE-->>FE: {messages, state: anonymous, requires_code_modal: false}

    User->>FE: gives the four identity fields
    FE->>BE: POST /api/chat {message}
    BE->>LLM: history + verify_identity, send_verification_code offered
    LLM-->>BE: tool_call verify_identity(first_name, last_name, address, phone_number)
    BE->>Tools: execute_tool -> authorize_tool_call
    Tools->>DB: match all four normalized fields, exactly one customer
    Tools-->>BE: {matched: true} (pending_customer_id set, state collecting_identity)
    BE->>LLM: tool result
    LLM-->>BE: tool_call send_verification_code()
    BE->>Tools: execute_tool -> authorize_tool_call
    Note over Tools: new 6-digit code, only its hash stored,<br/>expires in 300 s, 5 attempts.<br/>MOCK SMS log line. state awaiting_code
    Tools-->>BE: {sent: true, phone_last4, expires_in_seconds}
    BE->>LLM: tool result
    LLM-->>BE: text: a code was texted, use the popup
    BE-->>FE: {messages, state: awaiting_code, requires_code_modal: true}
    FE->>User: shows the 6-digit code modal

    User->>FE: enters the code in the modal
    FE->>BE: POST /api/verify {code} + session cookie
    Note over BE: check_verification_code (services/verification.py).<br/>Not a model tool. Expiry and attempts checked,<br/>customer_id = pending_customer_id, verified_at set
    BE-->>FE: {state: verified, verified_at}

    User->>FE: What is the status of FF751234951511?
    FE->>BE: POST /api/chat {message}
    BE->>LLM: verified system prompt + messages after verification + lookup_shipments offered
    LLM-->>BE: tool_call lookup_shipments(tracking_number)
    BE->>Tools: execute_tool -> authorize_tool_call
    Note over Tools: Enforcement point (F3):<br/>tool offered in this state?<br/>require_verified: state verified,<br/>customer_id and verified_at set.<br/>Only tracking_number is accepted.
    Tools->>DB: SELECT shipments WHERE customer_id = session.customer_id (+ tracking number if it appeared in the chat)
    DB-->>Tools: rows with packages
    Tools-->>BE: shipment and package fields only, no internal ids
    BE->>LLM: tool result
    LLM-->>BE: plain-language answer
    BE-->>FE: {messages, state: verified}

    alt the model sends a customer id or any other key
        LLM-->>BE: tool_call lookup_shipments(customer_id = someone else)
        BE->>Tools: execute_tool -> authorize_tool_call
        Tools-->>BE: DENIED forbidden_argument (logged with the key name only)
        BE->>LLM: {error: invalid_arguments, detail} - nothing is queried
    else the session is not verified
        BE->>Tools: lookup_shipments is not offered
        Tools-->>BE: DENIED not_offered -> {error: verification_required}
    end
```

Notes:

- The model gets up to `TOOL_CALL_MAX_ROUNDS` (4) rounds of tool calls per message, then a generic reply
  (`backend/services/chat.py:148-188`, `backend/config.py:19`).
- Every message about shipments runs a new `lookup_shipments`, so an admin change is visible on the visitor's **next**
  question; nothing is pushed to the browser (`backend/services/chat.py:53-54`).
- Log lines: `tool ALLOWED ...` / `tool DENIED ...` with names, states and argument shapes, never values
  (`backend/services/tools.py:397-426`).

Where to look: request/response models `backend/schemas.py:21-49`; route `backend/routers/chat.py:13-31`; tools and gate
`backend/services/tools.py:87-113, 133-136, 204-225, 315-347`; matching `backend/services/customer_match.py`; code check
`backend/services/verification.py:52-89`; verify route `backend/routers/verify.py:22-37`.
