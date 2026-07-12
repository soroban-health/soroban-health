# Architecture

## Overview

Soroban Health has three independently runnable pieces:

1. **Contract** (`contract/`) — a Rust/Soroban reference contract used as a
   test fixture for the scanner. It demonstrates paired good/bad
   implementations of each anti-pattern the scanner checks for; it is not a
   product contract.
2. **Backend** (`backend/`) — a FastAPI service exposing:
   - `app/services/analyzer.py` — static analysis over Rust source, looking
     for the three anti-patterns described in the README.
   - `app/services/scoring.py` — combines findings + test coverage into a
     single 0–100 health score, using a transparent, tunable formula.
   - `app/services/coverage.py` — parses `cargo tarpaulin` / `cargo llvm-cov`
     output into a coverage percentage, so callers can pass raw tool output
     instead of computing the number themselves.
   - `app/api/routes/` — HTTP surface (`/contracts`, `/scans`, `/health`).
3. **Frontend** (`frontend/`) — a Next.js dashboard that lets a developer
   paste a contract ID and source, trigger a scan, and see the resulting
   health score, findings, and score history.

## Data flow

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

`ContractRegisterRequest.contract_id` is validated against the Stellar
contract address format (56 characters, starting with `C`) before it's
accepted. `ScanSourceRequest` accepts either a `test_coverage_pct` directly
or raw `coverage_output` text from `cargo tarpaulin`/`cargo llvm-cov`, which
`services/coverage.py` parses into a percentage.

## Persistence

`/contracts/` and `/scans/` are backed by Supabase Postgres
(`backend/supabase/schema.sql`: `contracts`, `scans`, `findings` tables) via
`app/services/repository.py`'s `ContractRepository`, injected into routes
through `app/api/deps.py`. Running a scan upserts the contract's row first
(so scanning an unregistered `contract_id` still works), then persists the
scan and its findings — so `ContractSummary.latest_health_score` and
`last_scanned_at` reflect real scan history.

The test suite runs fully offline: `ContractRepository` takes an injected
Supabase client, and `tests/conftest.py` swaps in a small in-memory fake via
`app.dependency_overrides`, so `pytest` in CI needs no real credentials.

`GET /contracts/{contract_id}/scans` reads that history back
(`ContractRepository.list_scan_history`, ordered ascending by `scanned_at`)
for the dashboard's health-history chart (`HealthHistoryChart.tsx`). The
chart spaces points evenly by scan index rather than by elapsed time, since
the health-score trend — not scan cadence — is what the chart communicates.

## Static analysis

`app/services/analyzer.py` parses Rust source with `tree-sitter-rust` and
walks the resulting AST to find each anti-pattern, rather than scanning
source text with regexes. This means a `push_back` or `panic!` mentioned
inside a comment or string literal is not a match — only real AST nodes are.

"Nearby" (for example, does a `.set()` call have a matching `.extend_ttl()`)
is scoped to the enclosing function: each finding's context search walks up
to the nearest `function_item` and checks calls within it, rather than a
fixed line window. A TTL or eviction call that lives in a separate helper
function is not currently linked to the call site that needs it — tracking
that requires call-graph analysis (see Roadmap).

## Roadmap

- **Live Soroban RPC ingestion** — fetch a contract's on-chain event history
  and invocation/error-rate stats via `getEvents`/`getLedgerEntries`, and
  fold them into the health score alongside static findings.
- **Cross-function call-graph analysis** — link a TTL extension or eviction
  call in a helper function back to the storage write it applies to, so the
  analyzer isn't limited to single-function scope.
- **Paginated scan history** — `GET /contracts/{contract_id}/scans` returns
  the full history today; pagination will matter once contracts accumulate
  a large number of scans.
- **`tomllib`-based dependency parsing** — replace
  `check_dependency_version_drift`'s manual `Cargo.toml`/`Cargo.lock` text
  parsing with the standard library `tomllib` parser.
