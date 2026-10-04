# SecureShip

AI-gated shipment support chat application.

## Stack

- **Frontend:** React + TypeScript (Vite)
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL
- **LLM:** Ollama (`qwen3:8b`), runs locally on the host — NOT in Docker

## Running

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend: http://localhost:8000/health
- Postgres: localhost:5432

## Seed data

Section 4.4 mock data (customers, shipments, packages) — all invented, reproducible, safe to run twice:

```bash
docker compose exec backend python -m scripts.seed_data            # writes (upsert)
docker compose exec backend python -m scripts.seed_data --dry-run  # counts only
```

Script: `backend/scripts/seed_data.py`. Demo customers for verification: [`docs/demo-customers.md`](docs/demo-customers.md).
Prompt-injection test (another customer's data, Week 3): [`docs/security/prompt-injection-test.md`](docs/security/prompt-injection-test.md).
If the script reports duplicate customers (e.g. from an older seed), start from a clean dev database:
`docker compose down -v && docker compose up -d --build`, then seed again.

## Ollama

Ollama is not started via `docker-compose.yml`. It must be running
locally on the host (`ollama serve`, model `qwen3:8b`). The backend
reaches it via `host.docker.internal:11434`.

## Structure

```
secureship/
├── docker-compose.yml
├── docs/
│   ├── certificates/
│   └── diagrams/
├── frontend/
├── backend/
└── scripts/
```
