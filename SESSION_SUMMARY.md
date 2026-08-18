# Soroban Health — Session Summary

## 1. Codebase Exploration

Reviewed the full repository structure. Key findings:

**Architecture** — three independently runnable pieces:

| Layer | Stack | Location |
|---|---|---|
| Frontend | Next.js 14, TypeScript, Tailwind | `frontend/` |
| Backend | Python 3.12, FastAPI | `backend/` |
| Contract | Rust, Soroban SDK 21.7 | `contract/` |
| Database | Supabase (Postgres) | `backend/supabase/schema.sql` |

**Backend services** (`backend/app/services/`):
- `analyzer.py` — `tree-sitter-rust` AST analysis (not regex) for 3 anti-patterns
  plus a cross-file dependency-drift check
- `scoring.py` — transparent 0–100 formula: severity penalties, coverage
  modifier, on-chain error-rate penalty
- `rpc.py` — uses `getTransactions` + `fn_call` diagnostic events rather than
  `getEvents`, since most contracts never `publish`
- `github_fetch.py` — GitHub tarball endpoint (no `git clone` subprocess),
  bounded by three independent size/count caps
- `repository.py` — Supabase persistence; upserts contract row before scan

**Two gaps noted:**
- `frontend/lib/types.ts` doesn't mirror `on_chain_activity`, which the backend
  returns on every `ScanResult`
- `POST /scans/repo` has no client in `frontend/lib/api.ts` — the GitHub-scanning
  path is backend-only today

---

## 2. Dependency Installation

### Installed and verified

| Component | Version / Result | Verification |
|---|---|---|
| Backend deps | 58 packages in `backend/.venv` | **88/88 pytest pass** |
| Frontend deps | 390 packages via `npm ci` | `typecheck` + `lint` clean |
| Rust | 1.97.1, `x86_64-pc-windows-gnu` | `rustc`/`cargo` respond |
| Rust wasm target | `wasm32v1-none` | installed |
| stellar-cli | 27.0.0 (matches CI) | `stellar --version` OK |
| Contract wasm build | 3523 bytes, 8 exports | `stellar contract build` ✅ |
| Contract formatting | — | `cargo fmt --check` ✅ |

### Known broken

**`cargo test` fails.** The `backtrace` crate (via soroban-sdk testutils) needs
`dlltool` + `as` to build an import library for `dbghelp.dll`. Rustup's bundled
mingw ships `dlltool.exe` but no `as.exe`, so it fails with `CreateProcess`.
Affects native tests only — the wasm build path is unaffected.
`cargo clippy` was never verified and likely hits the same wall.

**Fix requires either:** installing mingw-w64 (~1GB, for `as.exe` + binutils),
or installing VS Build Tools (~2–4GB) and switching to the MSVC toolchain.

### Decisions and deviations

- **Chose `windows-gnu` over MSVC** — this machine has no MSVC build tools
  (no `link.exe`), and installing them would have been a multi-GB addition
  beyond the approved scope. This choice is the direct cause of the
  `cargo test` gap above.
- **Used Python 3.13**, the only version installed. The repo pins 3.12.7
  (`runtime.txt`) and CI uses 3.12. All wheels resolved as `cp313` binaries
  with no compilation, and the full suite passes — but this is a deviation
  from the pinned version.
- **A mingw-w64 install was started and then cancelled.** Nothing landed:
  `winget list` shows no package registered and no `gcc`/`as` on PATH.

### System changes made

- Created `~/.rustup` and `~/.cargo`; placed `stellar.exe` in `~/.cargo/bin`
- Appended `C:\Users\Josiah.Obaje\.cargo\bin` to the persistent **User PATH**
  (applies only to newly opened shells)
- Backend/frontend deps live inside the repo and are gitignored

---

## 3. Issue #21 — Dependency Version Drift

### Investigation

The issue was already implemented (commit `423b782`, released in v0.2.0).
Two of its acceptance criteria are not implementable as written: the
requested `check_dependency_drift(file_path, source)` signature and
`ALL_CHECKS` registration cannot work, because drift detection compares a
manifest against a lockfile while `ALL_CHECKS` runs per-file over Rust
sources. The existing cross-file design is the only workable shape.

### Bug found and fixed

The shipped check compared version strings directly. But a Cargo.toml
version string is a *requirement*, not a pin — `"21.7.0"` means `^21.7.0`
(`>=21.7.0, <22.0.0`). A lockfile resolving `21.7.7` is correct Cargo
behavior, yet was reported as MEDIUM drift (−5 health points). This repo's
own `contract/` workspace triggered it.

### Enhancements to `backend/app/services/analyzer.py`

- **Requirement matching** replaces string equality — caret (including the
  `0.x` / `0.0.x` rules), tilde, exact, wildcard, and comma-separated ranges
- **`tomllib` parsing** replaces hand-rolled line scanning, which also fixes
  `[dev-dependencies]`, `[target.'cfg(...)'.dependencies]`, and
  `{ workspace = true }` inheritance — the form `contract/reference` actually
  uses, and which the old parser could not follow
- **SemVer pre-release precedence** with Cargo's opt-in rule: `^21.7.0` does
  not match `22.0.0-rc.1`, but `^22.0.0-rc.1` matches `22.0.0-rc.2`. Relevant
  because soroban-sdk ships real release candidates
- **Fail-silent on uncertainty** — git/path dependencies, unsupported
  requirement forms, and malformed manifests yield no finding rather than a
  guess. `github_fetch.py` pulls arbitrary repos, so a broken manifest must
  not fail a scan or invent a finding
- **Deterministic ordering** (paths sorted) and findings that point at the
  real declaration line instead of a hardcoded line 1

### Compatibility

The public signature `check_dependency_version_drift(files: dict[str, str])`
is unchanged, so both callers (`app/api/routes/scans.py`, `scan_source_tree`)
are untouched. All 5 original tests pass unmodified, including the LOW
missing-`Cargo.lock` advisory.

**124 tests pass** (88 original + 36 new), `ruff` and `black --check` clean.

### Files changed

`backend/app/services/analyzer.py`, `backend/tests/test_analyzer.py`,
`CHANGELOG.md`, `docs/architecture.md`, `backend/README.md` (the last two
had described this work as still pending).

### Known limitations

- Only `soroban-sdk` is inspected; widening to every dependency needs a
  decision on how many findings one drifted lockfile should produce
- Missing `Cargo.lock` still emits a LOW advisory, which contradicts the
  issue's acceptance criteria — left as-is by your decision
