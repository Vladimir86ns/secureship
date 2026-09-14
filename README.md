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
