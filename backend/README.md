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

## Project layout

```
app/
  api/routes/    — FastAPI routers (contracts, scans, health)
  core/          — settings/config
  models/        — Pydantic request/response models
  services/      — analyzer (static checks) + scoring (health score formula)
tests/           — pytest suite, mirrors app/ structure
```

## Known gaps (good first issues!)

- `app/api/routes/contracts.py` uses an in-memory dict instead of Supabase — see open issues for wiring up real persistence.
- `app/services/analyzer.py` uses regex heuristics, not a real Rust AST parser. Swapping in `syn`-based parsing (likely via a small Rust subprocess or `tree-sitter-rust`) is a good medium/high-complexity issue.
- No RPC ingestion service yet (`app/services/rpc.py` does not exist) — pulling live on-chain events from Soroban RPC is the next major feature.
