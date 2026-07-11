# Soroban Health — Backend

FastAPI service powering contract scans, scoring, and the dashboard API.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Service info |
| GET | `/health/` | Liveness check |
| POST | `/contracts/` | Register a contract to track |
| GET | `/contracts/` | List tracked contracts |
| GET | `/contracts/{contract_id}` | Get one tracked contract |
| GET | `/contracts/{contract_id}/scans` | Health-score history for a tracked contract |
| POST | `/scans/` | Run a static-analysis scan against provided source files |

Interactive API docs are available at `/docs` once the server is running.

## Local development

```bash
pip install -r requirements.txt -r requirements-dev.txt --break-system-packages
cp .env.example .env  # fill in real values
uvicorn app.main:app --reload
pytest                # run the test suite
ruff check .          # lint
black --check .       # format check
```

## Database

Contracts, scans, and findings are persisted to Supabase Postgres. Apply
`supabase/schema.sql` once (via the Supabase SQL editor or
`psql "$SUPABASE_DB_URL" -f supabase/schema.sql`) against a fresh project,
then set `SUPABASE_URL` and `SUPABASE_KEY` (the project's **service_role**
key — Row Level Security is intentionally off for v0, since the backend is a
trusted server-side caller) in `.env`.

The test suite never touches a real Supabase project — `tests/conftest.py`
provides a `FakeSupabaseClient` double injected via `app.dependency_overrides`,
so `pytest` runs fully offline in CI.

## Project layout

```
app/
  api/routes/    — FastAPI routers (contracts, scans, health)
  api/deps.py    — shared FastAPI dependencies (repository injection)
  core/          — settings/config
  models/        — Pydantic request/response models
  services/      — analyzer, scoring, and Supabase-backed repository
tests/           — pytest suite, mirrors app/ structure
supabase/        — schema.sql (Postgres DDL for contracts/scans/findings)
```

## Known gaps (good first issues!)

- `check_dependency_version_drift` in `app/services/analyzer.py` does its own ad hoc `Cargo.toml`/`Cargo.lock` text parsing instead of using the stdlib `tomllib` — a good "good first issue" cleanup.
- No RPC ingestion service yet (`app/services/rpc.py` does not exist) — pulling live on-chain events from Soroban RPC is the next major feature.
