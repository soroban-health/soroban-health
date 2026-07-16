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

`POST /scans/repo` is the second entry point into the same scan+score
pipeline: it fetches a public GitHub repo's files server-side instead of
requiring the caller to paste them, then joins the same
`_scan_and_persist` path `POST /scans/` uses (see GitHub repository
scanning below).

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

## On-chain activity

`app/services/rpc.py`'s `SorobanActivityService` (injected via
`app/services/soroban_client.py` and `app/api/deps.py`, following the same
inject-the-client / fake-it-in-tests pattern as `ContractRepository`) pulls
a contract's recent invocation history from the single Soroban RPC endpoint
configured in `Settings.SOROBAN_RPC_URL`, for every `POST /scans/` request.

It does not use `getEvents`: that only surfaces events a contract
explicitly publishes via `env.events().publish(...)`, and most Soroban
contracts — including this repo's own `contract/reference` fixture — never
call that. Instead it calls `getTransactions` over a bounded, configurable
ledger window and decodes each transaction's `fn_call` diagnostic event to
find invocations of the target contract, combined with the transaction's
own `SUCCESS`/`FAILED` status. This gives real invocation frequency and
error rate, at the cost of scope limits stated here rather than left
implicit:

- `getTransactions` caps `limit` at 200 transactions per call, and testnet's
  network-wide transaction density is high and variable enough (measured
  10-30 transactions per ledger from unrelated activity) that the default
  lookback window only covers on the order of a few hundred ledgers
  (minutes), not hours — a `POST /scans/` request that needs to reach
  current activity can take upwards of 20-30 seconds. `ledgers_scanned_to`
  on the response reports the highest ledger actually reached, so a caller
  can tell if the fetch was cut short rather than assuming full coverage.
- Diagnostic events are provider-dependent — a third-party RPC provider may
  not return them, indistinguishable in the response shape from a
  genuinely idle contract.
- Only one network's RPC endpoint is queried per deployment — there is no
  `network -> RPC URL` map, since `ContractRegisterRequest.network` is a
  display label, not a routing key.

`compute_health_score` applies an error-rate penalty only once a contract
has at least 5 recorded invocations in the lookback window (too few
invocations make the rate unreliable — one failure out of two looks like a
50% error rate), and only for the error rate itself — invocation frequency
is surfaced in `ScanResult.on_chain_activity` for humans to read but doesn't
adjust the score, since there's no baseline for how much usage is "healthy."
An error rate of 0% is the expected reading for most contracts most of the
time: clients that simulate a call before submitting it (the norm) reject a
failing invocation before it ever reaches the ledger as a FAILED
transaction, so this module mostly has nothing to report — that is a
statement about how Soroban invocations work, not a gap in what it checks
for. When on-chain data can't be fetched at all (RPC unreachable, or the
contract isn't deployed to the configured network), the scan still
completes on static findings and coverage alone.

## GitHub repository scanning

`app/services/github_fetch.py` fetches a repo's `.rs`/`Cargo.toml`/
`Cargo.lock` files via GitHub's REST tarball endpoint
(`GET /repos/{owner}/{repo}/tarball[/{ref}]`), not a local `git clone`
subprocess. This avoids depending on a `git` binary at runtime and, more
importantly, avoids building a shell command around a user-supplied
`repo_url` at all — the URL is parsed into owner/repo/ref via a strict
regex, and only those validated pieces are used to construct our own
GitHub API request. Scope is `github.com` specifically, matching the
feature this implements; it is not a generic git-hosting client.

The fetch is bounded by three independent caps, each enforced as early as
possible: a compressed-download-size cap (checked per chunk while
streaming, not after buffering the whole response), a decompressed-size
cap (enforced via a byte-counting wrapper around the gzip stream, since
`tarfile` must decompress every byte to walk from one header to the next
even for files it discards — this is what actually bounds a
decompression-bomb-style payload), and a file-count cap. Exceeding any of
them fails the request with a 413 rather than exhausting server memory.
Unauthenticated requests to the GitHub API share a low rate limit; a
configured GitHub token would raise it substantially and is a natural
follow-up once usage warrants it, not something this needs today.

Scanning the same repo at different `ref`s (or a `contract_id` supplied
explicitly) writes to the same tracked contract by default — the most
recent scan's `health_score` is what `ContractSummary.latest_health_score`
shows, regardless of which ref produced it.

## Roadmap

- **Cross-function call-graph analysis** — link a TTL extension or eviction
  call in a helper function back to the storage write it applies to, so the
  analyzer isn't limited to single-function scope.
- **Paginated scan history** — `GET /contracts/{contract_id}/scans` returns
  the full history today; pagination will matter once contracts accumulate
  a large number of scans.
- **`tomllib`-based dependency parsing** — replace
  `check_dependency_version_drift`'s manual `Cargo.toml`/`Cargo.lock` text
  parsing with the standard library `tomllib` parser.
