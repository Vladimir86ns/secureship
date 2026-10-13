# 6.1 High-level system architecture

Regenerated against the implementation (Week 5).

What changed against the starting diagram: the chat is HTTP only (no WebSocket); there is no separate session store —
the session state and the transcript live in the same Postgres row (`chat_sessions`), keyed by an httpOnly cookie; the
code check is a backend service behind `POST /api/verify`, not a model tool; the human hand-off is a scripted step that
runs before the model; the admin gate is a router dependency (`require_admin`), not a middleware; Twilio is not used.

```mermaid
flowchart TB
    subgraph Browser["Browser (React 19 + Vite, port 5173)"]
        ChatUI["Chat window (App.tsx)"]
        Modal["6-digit code modal<br/>(VerificationModal.tsx)"]
        AdminUI["Admin panel /admin<br/>(lazy chunk with Auth0Provider)"]
    end

    subgraph Backend["Backend (FastAPI, port 8000)"]
        SessionDep["get_current_session<br/>(httpOnly cookie, dependencies.py)"]
        ChatAPI["POST /api/chat<br/>GET /api/session"]
        VerifyAPI["POST /api/verify<br/>POST /api/verify/resend<br/>POST /api/verify/cancel"]
        Escalation["Scripted human hand-off<br/>(escalation.py, regex, before the model)"]
        ToolLayer["Tool layer (services/tools.py)<br/>execute_tool -> authorize_tool_call<br/>-> require_verified"]
        Verification["services/verification.py<br/>(code hash, expiry, attempts)"]
        MockSMS["Mock SMS<br/>([MOCK SMS] log line)"]
        AdminAPI["/admin/* routes<br/>(customers, shipments, packages)"]
        AdminGate["require_admin<br/>(router dependency, Auth0 SDK)"]
    end

    subgraph Host["Host machine (not in Docker)"]
        Ollama["Ollama /api/chat<br/>model OLLAMA_MODEL (default qwen3:8b)"]
    end

    DB[("Postgres 16<br/>customers, shipments, packages,<br/>chat_sessions: state + JSONB transcript")]
    Auth0["Auth0<br/>(admin login ONLY)"]

    ChatUI -->|"message (cookie)"| ChatAPI
    ChatAPI --> SessionDep
    SessionDep <-->|"read / write session row"| DB
    ChatAPI -->|"wants a human, first time"| Escalation
    ChatAPI -->|"system prompt + history + tools for the state"| Ollama
    Ollama -->|"content or tool_calls"| ChatAPI
    ChatAPI -->|"every tool call"| ToolLayer
    ToolLayer -->|"lookup_shipments: WHERE customer_id = session.customer_id"| DB
    ToolLayer -->|"send_verification_code"| Verification
    Verification --> MockSMS
    ChatAPI -->|"requires_code_modal: true"| Modal
    Modal -->|"code / resend / start over (cookie)"| VerifyAPI
    VerifyAPI --> SessionDep
    VerifyAPI --> Verification

    AdminUI -->|"Universal Login redirect"| Auth0
    Auth0 -->|"access token (kept in memory)"| AdminUI
    AdminUI -->|"Bearer token, no cookie"| AdminAPI
    AdminAPI --> AdminGate
    AdminGate -.->|"JWKS / discovery"| Auth0
    AdminGate -->|"admin SPA token only"| DB

    style ToolLayer fill:#ffe6cc,stroke:#d79b00,stroke-width:2px
    style AdminGate fill:#ffe6cc,stroke:#d79b00,stroke-width:2px
```

Where to look:

- Chat route: `backend/routers/chat.py:13`; session route: `backend/routers/session.py:13`; verify routes:
  `backend/routers/verify.py:22, 40, 58`.
- Session from the cookie only: `backend/dependencies.py:20-50`. Session columns and the JSONB transcript:
  `backend/models.py:97-141`.
- Enforcement point: `authorize_tool_call` and `require_verified`, `backend/services/tools.py:320-347`.
- Escalation before the model: `backend/services/chat.py:141-143`, `backend/services/escalation.py:24-58`.
- Mock SMS: `backend/services/mock_sms.py:6-13`, called from `backend/services/verification.py:41`.
- Ollama call: `backend/ollama_client.py:15-56` (`think: true`); model setting `backend/config.py:9`.
- Admin gate: `backend/routers/admin.py:30`, `backend/admin_auth.py:53-71`; admin client without the cookie:
  `frontend/src/api/adminMutator.ts:20-35`.
