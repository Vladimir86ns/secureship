# Admin vs. chat identity — separation check (Week 4)

Section 8, Week 4: *"Confirm: no code path lets an admin 'become' a verified chat session, and no code path lets a chat
session reach admin routes."* Covers Epic E3, Epic E4 and Section 4.5 (the two identity systems stay separate).

| | Chat visitor | Admin |
|---|---|---|
| Identity | conversational: name, address, phone + 6-digit code (Epics B/C) | Auth0 login (Epic E1) |
| Credential the backend reads | httpOnly cookie → `chat_sessions` row (`backend/dependencies.py:20-50`) | `Authorization: Bearer <Auth0 access token>` (`backend/admin_auth.py:53`) |
| Routes | `/api/*` | `/admin/*` |
| Data reached | only the verified customer's shipments, via the tool layer (`backend/services/tools.py`) | customers, shipments, packages (CRUD) |

## How `/admin/*` is protected (Epic E3)

- `backend/routers/admin.py:30` — the router itself carries `dependencies=[Depends(require_admin)]`, so every route
  under `/admin` is protected, including any route added later. A test walks all routes and checks it.
- `backend/admin_auth.py:53` `require_admin`:
  1. Auth0's SDK (`auth0-fastapi-api`) validates the access token: RS256 signature against the tenant's JWKS, issuer,
     audience (`AUTH0_AUDIENCE`), expiry; symmetric (HS*) tokens are refused.
  2. Only tokens issued **to the admin SPA for a signed-in user**: `azp` must be `AUTH0_ADMIN_CLIENT_ID`, and
     client-credentials (machine-to-machine) tokens are refused (`admin_auth.py:64-65`) — 403 `not_admin`.
- Responses: no token 400 (`invalid_request`), bad/expired/foreign token 401 (`invalid_token`), not the admin app 403.
  Every refusal is logged without token contents:

```
WARNI [secureship.admin] admin DENIED status=400 error=invalid_request path=/admin/customers
INFO  [secureship.admin] admin UPDATE entity=shipment id=3f2a9c1e fields=status admin=8b1d0c2a
```

(`admin=` is a hash of the Auth0 user id; only field *names* are logged, never values.)

## Admin → chat: an admin cannot become a verified chat session

- The only way to `verified` is `POST /api/verify` → `check_verification_code`
  (`backend/services/verification.py:52-89`); it is the only code that sets `chat_sessions.customer_id` and the
  `verified` state (`:82`, `:87`), and it needs that session's cookie and the code.
- `/api/*` never reads the `Authorization` header: the session comes only from the cookie
  (`backend/dependencies.py:29`). An admin token sent to the chat changes nothing.
- The admin code (`admin_auth.py`, `admin_schemas.py`, `routers/admin.py`, `services/admin.py`,
  `services/customer_identity.py`) does not import `ChatSession`, the verification or tool modules, or
  `get_current_session`; the admin API has no endpoint for chat sessions. Admin calls never create a chat session or
  set a cookie.
- Deleting a customer unlinks its chat sessions (`ON DELETE SET NULL`, `backend/models.py:106-112`); a verified session
  left without `customer_id` fails closed in `require_verified` (`backend/services/tools.py:290`). It is never moved to
  another customer.

**Remaining risk (by role, not a code path):** an admin manages the data the chat checks identities against, e.g. could
change a customer's phone number. With mock SMS the code is in the backend log. This is a consequence of the admin role
and of mocked SMS, not a way for the admin's login to turn into a chat session.

## Chat → admin: a chat session cannot reach admin routes

- `/admin/*` requires an Auth0 access token; the session cookie is not read there (the admin router does not depend on
  `get_current_session`).
- The model has exactly three tools (`TOOLS`, `backend/services/tools.py:238`): `verify_identity`,
  `send_verification_code`, `lookup_shipments`. Any other name is refused as `unknown_tool` by
  `authorize_tool_call` (`:300-304`). No tool makes HTTP requests or calls admin code.
- The chat code (`services/tools.py`, `services/chat.py`, `services/verification.py`, `routers/chat.py`,
  `routers/verify.py`, `routers/session.py`, `dependencies.py`) does not import any admin module.

## Automated tests (no network, no real Ollama)

Auth0 is replaced by a local fake tenant (`backend/tests/admin_tokens.py`): a local RSA key, its JWKS and discovery
document served through the SDK's `custom_fetch` hook, so the SDK really validates every token. Any other URL fails the
test.

| File | What it shows |
|---|---|
| `backend/tests/test_admin_auth.py` | no token 400; not a JWT, wrong audience, expired, wrong issuer, other key, HS256, no `exp` → 401; another application / no `azp` / machine-to-machine → 403; valid admin token → 200; every `/admin` route (and no other) requires `require_admin` |
| `backend/tests/test_admin_chat_separation.py` | admin token on `/api/chat`, `/api/verify`, `/api/session` → still anonymous, `lookup_shipments` refused; admin calls create no chat session and no cookie; a verified chat cookie on `/admin/*` → 400/401/403; the model's tools are exactly three and an "admin" tool call is refused, nothing changes; static import checks both ways |
| `backend/tests/test_admin_customers.py` | deleting a customer unlinks its verified chat session, which then gets `verification_required` |

```bash
docker compose exec backend pytest -q tests/test_admin_auth.py tests/test_admin_chat_separation.py
```

## Manual check (filled in by the owner)

1. `curl -i http://localhost:8000/admin/customers` → 400.
2. With a verified chat session open in the browser, open `http://localhost:8000/admin/customers` in the same browser → 400 (the cookie is not enough).
3. (Once the admin UI exists — Week 4 frontend part.) Log in at `http://localhost:5173/admin`, change a shipment; the chat tab stays as it was (still verified as the same customer, or still anonymous).
4. `docker compose logs -f backend | grep -E 'secureship\.(admin|tools)'` during steps 1–3.

| Date | Step | Result | `secureship.admin` / `secureship.tools` log line(s) | Outcome |
|---|---|---|---|---|
| 2026-10-04 | 1 — `curl -i http://localhost:8000/admin/customers` (owner) | 400 | not recorded | pass |
| 2026-10-04 – 2026-10-06 | 3 — Auth0 login at `/admin` with email and password (owner, browser) | Login works. First attempt failed with Auth0 "Client is not authorized to access resource server"; fixed in Auth0 Dashboard: APIs → SecureShip API → Application Access → User-Delegated Access for the SecureShip Admin application | not recorded | pass |
| 2026-10-04 – 2026-10-06 | 3 — one edit each for a customer, a shipment and a package in the admin panel (owner, browser) | All three edits saved | not recorded | pass |
| 2026-10-04 – 2026-10-06 | 3 — two tabs: admin changes a shipment's status; the verified chat session, on its next question (owner, browser) | Chat shows the new status | not recorded | pass |
| 2026-10-06 | 1 — `curl -i http://localhost:8000/admin/customers` (owner) | 400 | not recorded | pass |
| 2026-10-06 | `pytest tests/test_admin_auth.py tests/test_admin_chat_separation.py` (owner) | 33 passed | — | pass |
| 2026-10-11 | 1 — `curl -i http://localhost:8000/admin/customers` | `HTTP/1.1 400 Bad Request` | `admin DENIED status=400 error=invalid_request path=/admin/customers` | pass |
| 2026-10-11 | `curl -i -H "Authorization: Bearer abc" http://localhost:8000/admin/customers` | `HTTP/1.1 401 Unauthorized` | `admin DENIED status=401 error=invalid_token path=/admin/customers` | pass |
| 2026-10-11 | `docker compose exec backend pytest -q` (full suite) | 129 passed, 1 warning | — | pass |
| 2026-10-11 | `npm run build` in the frontend container | built without errors | — | pass |
| — | 2 — verified chat session open, then `/admin/customers` in the same browser | not run | not run | not run |
| — | 4 — `docker compose logs -f backend` watched during the owner's steps 1–3 | not run | not run | not run |
