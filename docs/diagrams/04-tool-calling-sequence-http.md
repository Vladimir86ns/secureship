# 6.3 Tool-calling sequence (the gating enforcement point)

Source: `docs/SecureShip-5Week-Program.md`, section 6.3 (line 497). Copied verbatim as the starting reference.

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant BE as Backend (Chat API)
    participant Session as Session Store
    participant LLM as Local LLM (Ollama)
    participant Tools as Tool Layer
    participant DB as Database

    User->>FE: "Where's my package?"
    FE->>BE: POST /chat {message, session_id}
    BE->>Session: get session state
    Session-->>BE: state = "Anonymous"
    BE->>LLM: prompt + tool defs + state context
    LLM-->>BE: tool_call: request_identity_info()
    BE->>FE: assistant message asking for name/address/phone
    FE->>User: shows message

    User->>FE: provides name, address, phone
    FE->>BE: POST /chat {message, session_id}
    BE->>LLM: prompt with collected fields
    LLM-->>BE: tool_call: verify_identity(fields)
    BE->>Tools: verify_identity(fields)
    Tools->>DB: match against Customer table
    DB-->>Tools: match found: customer_id=123
    Tools->>Session: set pending_customer_id=123, state="CodeSent"
    Tools-->>BE: result: code sent (mocked)
    BE->>FE: trigger modal display
    FE->>User: shows 6-digit code modal

    User->>FE: enters code
    FE->>BE: POST /verify-code {code, session_id}
    BE->>Tools: check_verification_code(code, session_id)
    Tools->>Session: compare code, check expiry/attempts
    Session-->>Tools: match, not expired
    Tools->>Session: set state="Verified", customer_id=123
    Tools-->>BE: verified = true
    BE-->>FE: 200 OK, chat unlocked

    User->>FE: "What's the status of my shipment?"
    FE->>BE: POST /chat {message, session_id}
    BE->>Session: get session state
    Session-->>BE: state="Verified", customer_id=123
    BE->>LLM: prompt + tool defs + verified context
    LLM-->>BE: tool_call: lookup_shipments(customer_id=123)
    BE->>Tools: lookup_shipments(customer_id=123)
    Note over Tools: Enforcement point:<br/>Tools layer ALWAYS uses<br/>session.customer_id, never<br/>a customer_id argument<br/>supplied by the model/user
    Tools->>DB: SELECT * FROM shipments WHERE customer_id=123
    DB-->>Tools: shipment rows
    Tools-->>BE: shipment data
    BE->>LLM: tool result
    LLM-->>BE: natural-language answer
    BE->>FE: assistant message
    FE->>User: "Your shipment is out for delivery..."
```
