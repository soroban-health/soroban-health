# Seed Issues — Soroban Health

Copy each block below into a new GitHub issue. Labels are suggested;
adjust complexity (`good first issue` / `medium` / `high`) to match what
you'd assign on Drips Wave / GrantFox.

---

### 1. [good first issue] Add a `dependency_version_drift` check to the analyzer
**Labels:** `good first issue`, `enhancement`, `backend`
**Body:** `app/services/analyzer.py` defines `FindingType.DEPENDENCY_VERSION_DRIFT` in the model but no check function implements it yet. Add a check that parses `Cargo.toml` / `Cargo.lock` and flags when the locked `soroban-sdk` version doesn't match what's pinned in `Cargo.toml`, mirroring the pattern of the existing three checks. Add tests in `tests/test_analyzer.py` following the existing style.

---

### 2. [good first issue] Add a loading skeleton to the scan results view
**Labels:** `good first issue`, `enhancement`, `frontend`
**Body:** Right now `app/page.tsx` just shows "Scanning..." as button text while a scan runs. Add a simple skeleton/placeholder for the `HealthScoreGauge` and `FindingsList` area while `loading` is true, so the layout doesn't jump when results arrive.

---

### 3. [good first issue] Add an `ESLint` rule check for `console.log` in committed frontend code
**Labels:** `good first issue`, `tooling`
**Body:** Add a no-console ESLint rule (warn level) to `.eslintrc.json` so stray debug logging doesn't slip into PRs.

---

### 4. [medium] Persist scan results to Supabase instead of in-memory dict
**Labels:** `enhancement`, `backend`
**Body:** `app/api/routes/contracts.py` currently stores registered contracts in an in-memory `_REGISTRY` dict, and `/scans/` doesn't persist results at all. Design a `contracts` + `scans` + `findings` schema in Supabase Postgres, wire up `supabase-py`, and persist scan results so `ContractSummary.latest_health_score` and `last_scanned_at` actually populate from real data. See `docs/architecture.md` for context.

---

### 5. [medium] Add a contract health history chart to the dashboard
**Labels:** `enhancement`, `frontend`
**Body:** Once issue #4 (persistence) lands, add a simple line chart showing health score over time for a given contract ID, so users can see whether a contract's health is improving or regressing across scans.

---

### 6. [medium] Replace regex-based checks with `tree-sitter-rust` AST parsing
**Labels:** `enhancement`, `backend`
**Body:** `app/services/analyzer.py` is explicit that its regex/line-window approach is a heuristic v0. Investigate using `tree-sitter-rust` (Python bindings) to parse the actual AST and reduce false positives — e.g. a `push_back` call inside a comment or string literal currently could be misflagged. Keep the existing `Finding` model and `ALL_CHECKS` registration pattern so the API surface doesn't change.

---

### 7. [high] Build live Soroban RPC ingestion for on-chain event history
**Labels:** `enhancement`, `backend`, `high-complexity`
**Body:** Currently the scanner only analyzes pasted source text. Add `app/services/rpc.py` that, given a contract ID and network, calls Soroban RPC (`getEvents`, `getLedgerEntries`) to pull a contract's actual deployed state and invocation history, and surface invocation frequency / error rate as part of the health score (see `compute_health_score`'s docstring for where this plugs in).

---

### 8. [high] GitHub integration: scan a repo by URL instead of pasted source
**Labels:** `enhancement`, `backend`, `high-complexity`
**Body:** Add a `POST /scans/repo` endpoint that accepts a `repo_url`, shallow-clones it server-side (or uses the GitHub API to fetch file contents), runs the existing `scan_source_tree` across it, and returns the same `ScanResult` shape. This is the natural next step toward "point Soroban Health at any public Soroban project."

---

### 9. [medium] Add unit test coverage reporting integration
**Labels:** `enhancement`, `backend`
**Body:** `test_coverage_pct` in `ScanSourceRequest` currently has to be supplied manually by the caller. Add a way to compute this automatically from `cargo tarpaulin` or `cargo llvm-cov` output for a given contract repo, so the dashboard doesn't rely on self-reported coverage numbers.

---

### 10. [good first issue] Add contract ID format validation
**Labels:** `good first issue`, `bug`, `backend`
**Body:** `ContractRegisterRequest.contract_id` currently accepts any string. Add validation that it matches the Stellar contract address format (56 characters, starts with `C`) and return a clear 422 error otherwise.
