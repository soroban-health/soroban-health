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

## What's NOT wired up yet (by design, and tracked as issues)

- **No persistence.** `/contracts/` uses an in-memory dict. Wiring this to
  Supabase (schema: `contracts`, `scans`, `findings` tables) is a concrete,
  scoped issue — see `good first issue` / `enhancement` labels.
- **No live RPC ingestion.** The scanner currently takes pasted source, not
  a fetched repo + on-chain event history. Adding a `app/services/rpc.py`
  that calls Soroban RPC (`getEvents`, `getLedgerEntries`) for a given
  contract ID is the next big feature, and a good "high" complexity issue.
- **Regex-based analysis, not a real AST.** `app/services/analyzer.py` is
  explicit in its own docstring about this tradeoff. Swapping to an
  AST-based pass (via `tree-sitter-rust` or a small Rust helper binary
  using `syn`) would reduce false positives/negatives significantly.

## Why these design choices

- **Heuristic analyzer first, AST later:** shipping something real and
  testable now beats blocking on a more "correct" but unbuilt approach.
  The tradeoff is documented explicitly so it reads as a decision, not
  an oversight.
- **In-memory store first, Supabase later:** keeps the initial API
  contract reviewable and testable without requiring secrets/infra to
  run the test suite in CI.
