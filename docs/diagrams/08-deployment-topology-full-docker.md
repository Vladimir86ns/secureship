# 6.5 Deployment topology — Bonus tier (Ollama in Docker) — Not implemented

Regenerated against the implementation (Week 5). Spec reference: Section 6.5, bonus tier.

**Status: not implemented (optional bonus, not attempted).**

There is no diagram here on purpose. `docker-compose.yml` has three services — `frontend`, `backend`, `postgres` — and
no `ollama` service (`docker-compose.yml:1-60`). Ollama runs on the host and the backend reaches it through
`host.docker.internal:11434` (`OLLAMA_BASE_URL`, `docker-compose.yml:25, 37-38`). The real topology is diagram
[07](07-deployment-topology.md).
