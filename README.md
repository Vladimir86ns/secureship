# SecureShip

AI-gated shipment support chat aplikacija.

## Stack

- **Frontend:** React + TypeScript (Vite)
- **Backend:** FastAPI (Python)
- **Baza:** PostgreSQL
- **LLM:** Ollama (`qwen3:8b`), pokreće se lokalno na hostu — NE u Dockeru

## Pokretanje

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend: http://localhost:8000/health
- Postgres: localhost:5432

## Ollama

Ollama se ne pokreće kroz `docker-compose.yml`. Potrebno je da bude
pokrenuta lokalno na hostu (`ollama serve`, model `qwen3:8b`). Backend
joj pristupa preko `host.docker.internal:11434`.

## Struktura

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
