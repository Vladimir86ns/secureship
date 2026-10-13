# SecureShip

SecureShip is a support chat for shipments. Anyone can open the chat and ask general questions. To see shipment data,
the visitor proves who they are inside the conversation: first name, last name, address and phone number, then a
6-digit code sent by (mock) SMS and typed into a popup. Only after that can the assistant look up shipments, and only
that customer's own. The assistant is a local model run by Ollama (`qwen3:8b`). A separate admin panel, behind an
Auth0 login, manages customers, shipments and packages.

- Frontend: React 19 + TypeScript + Vite (`frontend/package.json:17, 28`)
- Backend: FastAPI, SQLAlchemy (async), Alembic (`backend/requirements.txt`)
- Database: PostgreSQL 16 (`docker-compose.yml:44`)
- Model: Ollama on the host, `OLLAMA_MODEL` (default `qwen3:8b`, `backend/config.py:9`)
- Admin login: Auth0, used only for `/admin` (`backend/admin_auth.py`)

## Contents

1. [Quick start](#quick-start)
2. [Auth0 setup (admin only)](#auth0-setup-admin-only)
3. [Try it](#try-it)
4. [How it works](#how-it-works)
5. [Design decisions](#design-decisions)
6. [Tests](#tests)
7. [Known limitations](#known-limitations)
8. [Repository layout](#repository-layout)
9. [Troubleshooting](#troubleshooting)

## Quick start

Prerequisites: Docker Desktop; [Ollama](https://ollama.com) installed **on the host** with the model pulled
(`ollama pull qwen3:8b`, then `ollama serve` or the Ollama app); an Auth0 tenant for the admin panel (next section).

```bash
cp .env.example .env          # then fill in the AUTH0_* and VITE_AUTH0_* values
docker compose up --build     # frontend, backend, postgres
docker compose exec backend python -m scripts.seed_data            # mock data (upsert, safe to run twice)
docker compose exec backend python -m scripts.seed_data --dry-run  # counts only
```

| What | URL |
|---|---|
| Chat | http://localhost:5173/ |
| Admin panel | http://localhost:5173/admin |
| Backend health | http://localhost:8000/health |
| OpenAPI | http://localhost:8000/openapi.json |
| Postgres | localhost:5432 |

- `docker compose up` starts three services; Ollama is **not** one of them. The backend reaches it at
  `host.docker.internal:11434` (`docker-compose.yml:25, 37-38`).
- The backend runs `alembic upgrade head` before it starts, so the schema is always current (`backend/Dockerfile:12`).
- Compose refuses to start if a required variable is missing from `.env` (the `:?` checks in `docker-compose.yml`).
- Seed data: 30 invented customers and 50 shipments, a fixed random seed and deterministic ids
  (`backend/scripts/seed_data.py:36-40`, `scripts/README.md`). Demo customers and their tracking numbers:
  [`docs/demo-customers.md`](docs/demo-customers.md).

## Auth0 setup (admin only)

Auth0 is used **only** by the admin panel. The chat never loads it and never reads a token. The tenant needs:

1. **Applications → Create Application → Single Page Application** (the admin app). Under its settings, set
   **Allowed Callback URLs** and **Allowed Logout URLs** to `http://localhost:5173/` — with the trailing slash, because
   the frontend sends exactly that (`frontend/src/admin/config.ts:8-11`).
2. **APIs → Create API.** Its identifier is the audience the admin tokens are issued for.
3. **APIs → (your API) → Application Access:** allow **User-Delegated Access** for the admin application. Without it the
   login fails with "Client is not authorized to access resource server" (recorded in
   [`docs/security/admin-separation.md`](docs/security/admin-separation.md), manual check table).
4. **User Management → Users:** create the admin user(s) (email and password).

Then fill in `.env` (all public values, no secrets; see `.env.example:18-29`):

| Variable | Read by | Value |
|---|---|---|
| `AUTH0_DOMAIN`, `VITE_AUTH0_DOMAIN` | backend, frontend | tenant domain, without `https://` |
| `AUTH0_AUDIENCE`, `VITE_AUTH0_AUDIENCE` | backend, frontend | the API identifier from step 2 |
| `AUTH0_ADMIN_CLIENT_ID`, `VITE_AUTH0_CLIENT_ID` | backend, frontend | the SPA's client id from step 1 |

Note: the backend accepts any signed-in user of that one admin application; there are no roles
(`backend/admin_auth.py:62-71`). Whoever can log in to the admin app is an admin.

## Try it

Watch the backend log in a second terminal:

```bash
docker compose logs -f backend | grep -E 'secureship\.(tools|admin|mock_sms)|MOCK SMS'
```

1. Open http://localhost:5173/ and ask a general question — the assistant answers.
2. Ask "Where is my package?" — the assistant does not answer; it asks for your name, address and phone number.
3. Give the details of **Dana Demo** (`docs/demo-customers.md`): Dana, Demo, `100 Demo Plaza, Springfield, IL 62701`,
   `217-555-0100`. The log shows `tool ALLOWED name=verify_identity`, `tool ALLOWED name=send_verification_code` and
   `[MOCK SMS] to … Your SecureShip verification code is …`. The code popup opens.
4. Type a wrong code once ("That code was incorrect"), then the right one — "✓ Identity verified".
5. Ask "What's the status of FF751234951511?" — the log shows `tool ALLOWED name=lookup_shipments
   scope=session.customer_id tracking_filter=yes results=1`.
6. In a second tab open http://localhost:5173/admin → **Log in** → Shipments. Type `FF75` (or `ff-751`) in the search
   box, change the status of FF751234951511, Save. The log shows `admin UPDATE entity=shipment … fields=status`.
7. Back in the chat, ask again ("And now?") — the answer shows the new status. There is no push: the change is seen on
   the **next** question.

Edge cases to try: close the code popup and use **Enter code** in the header to reopen it; **Start over** in the popup
goes back to the beginning; wait more than 5 minutes (or use up the 5 attempts) and send a chat message — verification
restarts and asks for your details again.

## How it works

Diagrams, regenerated against the code: [`docs/diagrams/`](docs/diagrams/README.md).

### Conversation states

`anonymous → collecting_identity → (code_sent) → awaiting_code → verified`, plus `escalated_to_human` during the
scripted hand-off (`backend/models.py:16-22`; diagram
[02](docs/diagrams/02-conversation-state-machine.md)).

- The session is a row in `chat_sessions`, found by an httpOnly cookie (30 days). The cookie is only a random lookup
  key, so the browser cannot claim to be verified (`backend/dependencies.py:12, 20-50`). There are no visitor accounts:
  a new browser or a cleared cookie is a new anonymous session and needs a new verification.
- Identity matches only if all four fields match exactly one customer after normalization (case, spaces,
  punctuation, phone format). Abbreviations are not expanded (`backend/services/customer_match.py:8-23`,
  `backend/services/normalization.py:10-38`). A failed match gets a neutral reply that never says which field was
  wrong or whether the customer exists (`backend/services/chat.py:36-38`).
- The code is checked only by `POST /api/verify` → `check_verification_code`, never by the model and never typed in the
  chat. That is the only code that sets `customer_id` and the `verified` state
  (`backend/services/verification.py:52-89`, `backend/routers/verify.py:22-37`).
- The whole transcript is stored as JSONB on the session row. Internal events (state changes, verification outcomes)
  are kept for audit and filtered out of every API response (`backend/models.py:139-141`,
  `backend/services/transcript.py:14-26`).

### The three tools and the enforcement point

The model has exactly three tools, and the backend decides per state which ones it even sees
(`backend/services/tools.py:257-317`):

| Tool | Offered in | What it does |
|---|---|---|
| `verify_identity` | `anonymous`, `collecting_identity` | matches the four fields; stores only a *pending* customer |
| `send_verification_code` | same, and only after a match | new code, hash stored, `[MOCK SMS]` log line, `awaiting_code` |
| `lookup_shipments` | `verified` | the visitor's own shipments; optional `tracking_number` |

Every tool call goes through `execute_tool → authorize_tool_call`, and shipment tools additionally through
`require_verified` (`backend/services/tools.py:320-347`). `lookup_shipments` has no customer argument at all: any other
key is refused as `forbidden_argument`, and the query is always `WHERE customer_id = session.customer_id`
(`tools.py:170-180, 204-225`). A tracking number is used only if it actually appeared in this conversation
(`tools.py:157-163, 211-217`). The model gets only the Section 4.4 fields, no internal ids (`tools.py:183-201`).
Attempts to get another customer's data are documented in
[`docs/security/prompt-injection-test.md`](docs/security/prompt-injection-test.md).

### Human hand-off

Asking for a human (regex on `human`, `agent`, `representative`, `real person`, `speak to someone`) plays a scripted,
cosmetic hand-off before the model is called: five messages, an agent name picked at random, and the chat window
changes color. It never touches `customer_id` or `verified_at`, so the tools and the gate behave exactly as before
(`backend/services/escalation.py:10-58`, `backend/services/chat.py:141-143`; diagram
[03](docs/diagrams/03-human-escalation-sequence.md)).

### Frontend

- Chat (`frontend/src/App.tsx`): the code popup opens when a response says `requires_code_modal`; the **Enter code**
  button reopens it; messages of the hand-off are revealed 500 ms apart. The chat scrolls to the newest message after
  you send, shows the bottom after a reload, and follows new messages only while you are near the bottom — if you
  scrolled up to read, it leaves you there (`App.tsx:62-82`).
- Code popup (`frontend/src/components/VerificationModal.tsx`): enter code, **Resend** (after 30 s), **Start over**.
- Admin (`frontend/src/admin/`): customers, shipments and packages (list, create, edit, delete). Each list has a search
  box that filters the already loaded list in the browser — case-insensitive, and tracking numbers match with or without
  spaces and dashes (`frontend/src/admin/search.ts`). The toolbar above the table stays at the top while scrolling.
- API types and React Query hooks are generated by Orval from `/openapi.json`; the admin endpoints use their own client
  that sends the Bearer token and never the chat cookie (`frontend/orval.config.ts`, `frontend/src/api/adminMutator.ts`).
  Regenerate with `npm run generate:api` in `frontend/` while the backend is running.

## Design decisions

**HTTP instead of WebSocket.** One `POST /api/chat` returns the assistant's messages and the new state. It is simpler,
fully covered by the generated Orval client, and good enough for this flow: every shipment question runs a fresh
`lookup_shipments`, so an admin change is visible on the next question (`backend/services/chat.py:53-54`). Nothing is
pushed to an open chat. The WebSocket variant (diagram 05) was not built.

**Verification code rules** (`backend/config.py:15-17`, `backend/services/verification.py`):

- 6 digits, only the SHA-256 hash is stored, compared in constant time (`verification.py:12-21`).
- Expires after **300 s**; **5** attempts per code.
- **Resend** is allowed after **30 s**; it issues a new code and resets the attempts. The number of resends is
  deliberately **not limited** — each code is still limited by time and attempts, and the SMS is a mock
  (`verification.py:148-161`).
- An expired or used-up code + the next chat message → back to `collecting_identity`, the typed details are forgotten,
  and the visitor is told why (`verification.py:104-126`, called at `backend/services/chat.py:139`).
- **Start over** (`POST /api/verify/cancel`) → `anonymous`; refused for a verified session (`verification.py:129-145`).
- Input limits: a chat message is at most 2000 characters, and the code must be exactly 6 digits — checked before the
  code check, so a malformed code never uses an attempt (`backend/schemas.py:6, 21-22, 42-44`).

**Target response time: 30 s per chat answer** on the machine below. It is the longest measured time (27.5 s) rounded up
to the next 5 s.

| | |
|---|---|
| Date | 2026-10-13 |
| Machine | Apple M4 Pro, 12 cores, 24 GB RAM, macOS 15.7.9 |
| Model | `qwen3:8b` (Q4_K_M, 8.2B), Ollama 0.33.2 on the host, `think: true` (`backend/ollama_client.py:22-31`) |
| Method | one session through the real API, verified as Dana Demo, then 5 questions; time from sending `POST /api/chat` to the full response |
| Results | shortest 14.8 s, longest 27.5 s, average 19.7 s |

| # | Question | Time |
|---|---|---|
| 1 | What are my shipments? | 27.5 s |
| 2 | Where is FF751234951511? | 19.8 s |
| 3 | Is anything wrong with any of my deliveries? | 16.1 s |
| 4 | What are my shipments? | 14.8 s |
| 5 | Where is FF751234951511? | 20.6 s |

In run 4 the model returned an empty reply twice (the backend retries once) and the visitor got "Could you rephrase
that?" (`backend/services/chat.py:151-168`). The time is long mostly because thinking is on; with thinking off,
`qwen3:8b` stopped calling tools (`backend/ollama_client.py:26-31`).

**One enforcement point.** Whether a tool may run is decided in one place: `authorize_tool_call` and
`require_verified` in `backend/services/tools.py:320-347`. The prompts tell the model the rules, but nothing depends on
the model following them (`backend/tests/test_tool_gate.py`, `backend/tests/test_prompt_injection.py`).

**Admin and chat are separate identity systems.** `/admin/*` is protected by `require_admin` on the whole router
(`backend/routers/admin.py:30`): a valid Auth0 access token issued to the admin SPA for a signed-in user;
machine-to-machine tokens are refused (`backend/admin_auth.py:53-71`). No token → 400, bad token → 401, another
application → 403. The chat routes read only the cookie, never `Authorization` (`backend/dependencies.py:29`); the admin
client never sends the cookie (`frontend/src/api/adminMutator.ts:20-23`); the chat page never loads the Auth0 code
(`frontend/src/main.tsx:8-9`). Details and checks: [`docs/security/admin-separation.md`](docs/security/admin-separation.md).

**Logs without personal data.** Tool logs contain tool names, states, argument *names and types*, and result counts —
never values (`backend/services/tools.py:375-426`). Admin logs contain the entity, a short id, the changed field
*names* and a hash of the admin's Auth0 id (`backend/services/admin.py:32`, `backend/admin_auth.py:40-43`). Ollama
diagnostics are numbers only (`backend/ollama_client.py:47-55`). The one deliberate exception is the `[MOCK SMS]` line,
which contains the phone number and the code because it *is* the simulated SMS (`backend/services/mock_sms.py:6-13`).

**Ollama on the host.** The baseline setup of Section 6.5: the model runs on the host (with the Mac's GPU), and the
backend calls it through `host.docker.internal` (diagram [07](docs/diagrams/07-deployment-topology.md)). Ollama in
Docker was the optional bonus and was not built (diagram 08).

## Tests

```bash
docker compose exec backend python -m pytest -q
```

154 passed on 2026-10-13. No test calls a real model or the real Auth0 tenant:

- the model is a fake: `services.chat.chat_completion` is replaced with an `AsyncMock` that returns scripted replies
  and tool calls (`backend/tests/helpers.py:28-41`);
- Auth0 is a local fake tenant (own RSA key, JWKS and discovery served through the SDK's `custom_fetch`), and any other
  network fetch fails the test (`backend/tests/conftest.py:24-43`, `backend/tests/admin_tokens.py`).

They cover: normalization and identity matching, the verification flow and code rules, the edge cases (expired or
used-up code, Start over, malformed input and tool calls, empty states — `test_edge_cases.py`), the tool gate and
prompt injection, the tool-call cap, empty model replies, escalation, transcript storage, the admin API and its auth,
admin/chat separation, and the seed script. Frontend: `npm run build` and `npm run lint` in `frontend/`.

## Known limitations

- **A verified session never expires.** It stays verified as long as the cookie lives (30 days); `ended_at` exists but
  is never written (`backend/models.py:137`, `backend/dependencies.py:12`).
- **If Ollama is down, the chat returns HTTP 500 and the message is lost.** Connection and HTTP errors from Ollama are
  not caught; only malformed responses are (`backend/ollama_client.py:36-46`, `backend/services/chat.py:159-163`).
- **Tool calls are not stored in the transcript.** They are only in the log; the transcript records state changes and
  verification outcomes.
- **The mock SMS goes to the number the visitor typed,** not to the stored one (`backend/services/verification.py:41`).
  A match requires the same number after normalization, so it is the same number, possibly in another format.
- **The hand-off regex has false positives.** Any message containing a word like "agent" or "human" starts the
  hand-off, e.g. "my shipping agent said…" (`backend/services/escalation.py:10-12`). It runs once per session.
- **Name in one piece.** Matching needs first and last name separately; whether the model splits "Dana Demo" correctly
  depends on the model.
- **`escalated_to_human` is not a lasting state.** The session goes back to its previous state in the same request; the
  lasting trace is `escalated_to_human_at` (`backend/services/escalation.py:34-35, 55-58`).

## Repository layout

```
secureship/
├── docker-compose.yml          frontend, backend, postgres
├── .env.example
├── backend/
│   ├── main.py                 app, CORS, routers, /health
│   ├── config.py               settings from the environment
│   ├── dependencies.py         chat session from the cookie
│   ├── models.py               SQLAlchemy models
│   ├── schemas.py, admin_schemas.py
│   ├── admin_auth.py           require_admin (Auth0)
│   ├── ollama_client.py
│   ├── routers/                chat, session, verify, admin
│   ├── services/               chat, tools, verification, escalation, transcript, matching, admin, mock_sms
│   ├── alembic/                migrations
│   ├── scripts/seed_data.py    mock data
│   └── tests/
├── frontend/
│   ├── orval.config.ts
│   └── src/
│       ├── App.tsx             chat
│       ├── components/         code popup
│       ├── admin/              admin panel (Auth0)
│       └── api/                Orval output + the two axios clients
├── docs/
│   ├── diagrams/               Section 6 diagrams, regenerated (Week 5)
│   ├── security/               admin separation, prompt-injection test
│   └── demo-customers.md
└── scripts/README.md           where the seed script lives
```

## Troubleshooting

- **Chat answers with an error / HTTP 500:** Ollama is not running on the host or the model is missing. Check
  `curl http://localhost:11434/api/tags` and `ollama pull qwen3:8b`.
- **The seed script reports duplicate customers** (e.g. from an older seed): start from a clean database —
  `docker compose down -v && docker compose up -d --build`, then seed again. Duplicates would make identity matching
  fail closed (`backend/scripts/seed_data.py:13-16`).
- **Verification never matches:** type the address exactly as in `docs/demo-customers.md` ("Street", not "St").
- **Where is the code?** `docker compose logs -f backend | grep "MOCK SMS"`.
- **Admin login: "Client is not authorized to access resource server":** allow User-Delegated Access for the admin
  application on the API (Auth0 setup, step 3).
- **Admin login redirects fail:** the Allowed Callback and Logout URLs must be `http://localhost:5173/` with the
  trailing slash.
- **`/admin/*` answers 400/401/403:** no token / invalid or expired token / a token from another application.
