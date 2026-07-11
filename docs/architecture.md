# Architecture

## Overview

Soroban Health has three independently runnable pieces:

1. **Contract** (`contract/`) — a Rust/Soroban reference contract used as a
   test fixture for the scanner. It is *not* meant to be deployed as a
   product contract; it exists to demonstrate good/bad pattern pairs.
2. **Backend** (`backend/`) — a FastAPI service exposing:
   - `app/services/analyzer.py` — static analysis over Rust source, looking
     for the three anti-patterns described in the README.
   - `app/services/scoring.py` — combines findings + test coverage into a
     single 0–100 health score, using a transparent, tunable formula.
   - `app/api/routes/` — HTTP surface (`/contracts`, `/scans`, `/health`).
3. **Frontend** (`frontend/`) — a Next.js dashboard that lets a developer
   paste a contract ID and source, trigger a scan, and see the resulting
   health score and findings.

## Data flow (current state)

```
User pastes Rust source in the dashboard
        │
        ▼
POST /scans/  { contract_id, files: { "lib.rs": "..." } }
        │
        ▼
analyzer.scan_file()  → list[Finding]
        │
        ▼
scoring.compute_health_score()  → float (0-100)
        │
        ▼
ScanResult returned to frontend → HealthScoreGauge + FindingsList render it
```

## Persistence

`/contracts/` and `/scans/` are backed by Supabase Postgres
(`backend/supabase/schema.sql`: `contracts`, `scans`, `findings` tables) via
`app/services/repository.py`'s `ContractRepository`, injected into routes
through `app/api/deps.py`. Running a scan upserts the contract's row first
(so scanning an unregistered `contract_id` still works), then persists the
scan and its findings — so `ContractSummary.latest_health_score` and
`last_scanned_at` reflect real scan history.

The test suite stays fully offline: `ContractRepository` takes an injected
Supabase client, and `tests/conftest.py` swaps in a small in-memory fake via
`app.dependency_overrides`, so `pytest` in CI needs no real credentials.

`GET /contracts/{contract_id}/scans` reads that history back
(`ContractRepository.list_scan_history`, ordered ascending by `scanned_at`)
for the dashboard's health-history chart (`HealthHistoryChart.tsx`). The
chart spaces points evenly by scan index rather than literal elapsed time —
a deliberate v0 simplification (irregular scan cadence will read as visually
uniform), acceptable since the Y-axis (the health score trend) is what the
issue actually cares about. No pagination on this endpoint yet — a known gap
once contracts accumulate a large scan history.

## What's NOT wired up yet (by design, and tracked as issues)

- **No live RPC ingestion.** The scanner currently takes pasted source, not
  a fetched repo + on-chain event history. Adding a `app/services/rpc.py`
  that calls Soroban RPC (`getEvents`, `getLedgerEntries`) for a given
  contract ID is the next big feature, and a good "high" complexity issue.

## Why these design choices

- **`tree-sitter-rust` for the analyzer, not a `syn`-based subprocess:**
  `app/services/analyzer.py` parses a real Rust AST via `tree-sitter-rust`
  rather than the regex/line-window heuristics it started with. Syntax-only
  parsing is sufficient here since these are pattern checks (does a `.set(`
  have a matching `.extend_ttl(` in the same function?), not semantic ones —
  and `tree-sitter-rust` ships as a precompiled wheel for the CI matrix,
  unlike a `syn`-based approach which would need a Rust toolchain and a
  cross-process boundary in the Python service. "Nearby" now means *the
  enclosing function* rather than a fixed line window, which fixes both the
  false positives the old heuristic had (a `push_back` mentioned in a
  comment or string literal isn't a real AST node) and a false negative it
  had (two short functions sitting close together could let an unrelated
  call in the next function satisfy the window). The known remaining gap:
  a TTL/eviction call living in a *sibling helper function* still won't be
  picked up — that's call-graph analysis, a separate future issue.
- **Injected client + dependency override, not an in-memory fallback:**
  `ContractRepository` always talks to a real Supabase client in production;
  tests fake only the client itself (`tests/conftest.py`). This avoids a
  second, divergent in-memory code path that could drift from what actually
  runs in production, while still keeping the test suite free of real
  secrets/infra.
