# 6.5 Deployment / local dev topology

Regenerated against the implementation (Week 5). Spec reference: Section 6.5 (baseline tier).

Differences from the starting diagram: the frontend is the Vite dev server on port 5173 (not 3000); the browser loads
the app from 5173 but calls the API on 8000 directly (CORS allows `FRONTEND_ORIGIN`); REST/JSON only; Auth0 is used by
the browser (login) and by the backend (keys for token validation); Twilio is not used.

```mermaid
flowchart LR
    subgraph DevMachine["Developer machine"]
        direction TB

        subgraph Compose["docker compose up (3 services)"]
            direction TB
            FE["frontend container<br/>Vite dev server :5173<br/>(npm run dev)"]
            BE["backend container :8000<br/>alembic upgrade head, then uvicorn --reload"]
            PG[("postgres:16-alpine :5432<br/>volume postgres_data, healthcheck")]
        end

        Browser["Browser<br/>chat: http://localhost:5173/<br/>admin: http://localhost:5173/admin"]
        OllamaHost["Ollama on the HOST (not in Docker)<br/>:11434, model qwen3:8b"]
    end

    Auth0["Auth0 tenant<br/>(admin login only)"]

    Browser -->|"loads the app"| FE
    Browser -->|"REST/JSON: /api/* with cookie,<br/>/admin/* with Bearer token"| BE
    BE -->|"host.docker.internal:11434"| OllamaHost
    BE -->|"starts after postgres is healthy"| PG
    Browser -.->|"Universal Login (admin only)"| Auth0
    BE -.->|"JWKS / discovery for token validation"| Auth0

    style Compose fill:#e6f2ff,stroke:#3380cc,stroke-width:2px
    style OllamaHost fill:#fff4e6,stroke:#cc8800,stroke-width:2px
```

Where to look: `docker-compose.yml:1-60` (ports `:5`, `:20`, `:46`; `OLLAMA_BASE_URL` `:25`; `extra_hosts` `:37-38`;
`service_healthy` `:39-41`); `backend/Dockerfile:12`; `frontend/Dockerfile:10-12`; API base URL
`frontend/src/api/mutator.ts:3-8`; CORS `backend/main.py:16-22`; Auth0 in the browser `frontend/src/admin/AdminRoot.tsx`;
Auth0 in the backend `backend/admin_auth.py:23-33`.
