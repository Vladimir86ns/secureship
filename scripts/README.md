# scripts

The mock data generation script (Section 4.4) lives in the backend so it can use the backend's models and database
session inside the container: **`backend/scripts/seed_data.py`**.

```bash
docker compose up -d --build
docker compose exec backend python -m scripts.seed_data            # 30 customers, 50 shipments, ~85 packages (upsert)
docker compose exec backend python -m scripts.seed_data --dry-run  # counts only
```

Reproducible (fixed seed, deterministic ids) and safe to run twice. Demo customers: `docs/demo-customers.md`.
