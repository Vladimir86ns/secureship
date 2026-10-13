# 6.4 Data model (ERD)

Regenerated against the implementation (Week 5). Spec reference: Section 6.4. Source of truth: `backend/models.py` and
the Alembic migrations in `backend/alembic/versions/`.

Differences from the starting diagram: customers also store normalized copies of the four identity fields (indexed,
used for matching); `status` and `state` are Postgres enums; a chat session links to a customer in **two** ways (the
pending match, and the verified customer); the code and the typed identity live on the session row; there is no
`ADMIN_USER` table — admins exist only in Auth0.

```mermaid
erDiagram
    CUSTOMER ||--o{ SHIPMENT : "has (ON DELETE RESTRICT)"
    SHIPMENT ||--o{ PACKAGE : "contains (ON DELETE CASCADE)"
    CUSTOMER |o--o{ CHAT_SESSION : "verified as, customer_id (SET NULL)"
    CUSTOMER |o--o{ CHAT_SESSION : "pending match, pending_customer_id (SET NULL)"

    CUSTOMER {
        uuid id PK
        string first_name
        string last_name
        string address
        string phone_number
        string normalized_first_name "indexed"
        string normalized_last_name "indexed"
        string normalized_address "indexed"
        string normalized_phone_number "indexed"
        timestamptz created_at
    }
    SHIPMENT {
        uuid id PK
        uuid customer_id FK "indexed"
        string tracking_number UK
        shipment_status status "label_created, in_transit, out_for_delivery, delivered, exception"
        string carrier
        string origin
        string destination
        date estimated_delivery
        timestamptz last_update
    }
    PACKAGE {
        uuid id PK
        uuid shipment_id FK "indexed"
        string description
        numeric weight_kg "Numeric(8,3)"
        numeric declared_value "Numeric(10,2)"
    }
    CHAT_SESSION {
        uuid id PK
        string session_token UK "httpOnly cookie value"
        uuid pending_customer_id FK "set by verify_identity on a match"
        uuid customer_id FK "set only by check_verification_code"
        session_state state "anonymous, collecting_identity, code_sent, awaiting_code, verified, escalated_to_human"
        timestamptz verified_at
        timestamptz escalated_to_human_at
        string escalated_agent_name
        string pending_first_name
        string pending_last_name
        string pending_address
        string pending_phone_number
        string code_hash "SHA-256, never the code"
        timestamptz code_expires_at
        int code_attempts
        int code_max_attempts
        timestamptz code_last_sent_at
        timestamptz started_at
        timestamptz ended_at "exists, not written yet"
        jsonb transcript "visible messages + internal events"
    }
```

Notes:

- Columns and keys: `backend/models.py:35-141` (enums `:16-32`, foreign keys `:63-66`, `:87-89`, `:105-113`).
- A customer with shipments cannot be deleted; the admin API answers 409 `customer_has_shipments`
  (`backend/services/admin.py:118-125`). Deleting a customer sets both session links to NULL; a verified session left
  without `customer_id` fails closed in `require_verified` (`backend/services/tools.py:320-327`).
- The transcript is one JSONB list per session. Entries with an `event` key (state changes, verification outcomes, the
  tool-call cap) are internal and are filtered out of every API response (`backend/services/transcript.py:14-26`).
- Admin identity: Auth0 only. The backend stores no admin rows; logs carry a short hash of the Auth0 user id
  (`backend/admin_auth.py:36-43`).
