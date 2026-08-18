# Changes — dependency drift check

All changes are uncommitted in the working tree.

| File | +/− | What |
|---|---|---|
| `backend/app/services/analyzer.py` | +348 −65 | Rewrote `check_dependency_version_drift` |
| `backend/tests/test_analyzer.py` | +194 −0 | 36 new tests (16 → 52 in this file) |
| `docs/architecture.md` | +32 −3 | New "Dependency drift" section; roadmap updated |
| `CHANGELOG.md` | +8 −0 | Entry under Unreleased → Fixed |
| `backend/README.md` | +2 −1 | Replaced a known-gaps entry that this work closed |
| `SESSION_SUMMARY.md` | +56 −31 | Refreshed; prior text had become false |

Test suite: **88 → 124 passing**. `ruff check` and `black --check` clean.

---

## The bug

A Cargo.toml version string is a *requirement*, not a pin. `soroban-sdk = "21.7.0"`
means `^21.7.0`, i.e. `>=21.7.0, <22.0.0`. The check compared the two strings
directly, so a lockfile resolving `21.7.7` — normal, correct Cargo behavior —
was reported as drift.

This fired on the repo's own `contract/` workspace:

```
MEDIUM Cargo.lock: Dependency version drift detected. Cargo.toml pins
soroban-sdk to '21.7.0', but Cargo.lock resolves it to '21.7.7'.
```

Every routine patch bump cost a MEDIUM finding (−5 health points) for code that
was fine. After the change, the same workspace reports 0 findings, and an
injected `soroban-sdk` major bump is still flagged correctly.

---

## `backend/app/services/analyzer.py`

### Requirement matching replaces string equality

Drift now means *the lockfile violates the requirement*. Supported comparator
forms:

| Form | Example | Meaning |
|---|---|---|
| Caret (default) | `21.7.0`, `^21.7.0` | `>=21.7.0, <22.0.0` |
| Caret on `0.x` | `0.2.3` | `>=0.2.3, <0.3.0` |
| Caret on `0.0.x` | `0.0.3` | `>=0.0.3, <0.0.4` |
| Tilde | `~21.7` | `>=21.7.0, <21.8.0` |
| Exact | `=21.7.0` | exactly `21.7.0` |
| Wildcard | `21.*`, `*` | `>=21.0.0, <22.0.0`; any |
| Range | `>=21.0, <22.0` | conjunction of comparators |

Whether a component was written is preserved, because Cargo reads `~1` (`<2.0.0`)
differently from `~1.0` (`<1.1.0`) — a missing minor is not an implicit zero.

### `tomllib` parsing replaces hand-rolled line scanning

This was already queued as a cleanup in `backend/README.md` and the architecture
roadmap. It also fixes real gaps the line-based parser had:

- `[dev-dependencies]` and `[build-dependencies]`
- `[target.'cfg(...)'.dependencies]`
- **Workspace inheritance** — `{ workspace = true }` now resolves to the root's
  `[workspace.dependencies]`. This is exactly how `contract/reference/Cargo.toml`
  declares its dependency, and the old parser could not follow it.

A workspace root's declaration wins, since it is the single source of truth for
members that inherit from it.

### SemVer pre-release precedence, with Cargo's opt-in rule

Pre-release tags were previously stripped, so `22.0.0-rc.1` was treated as plain
`22.0.0`. Now:

- A pre-release ranks below its own release (`1.0.0-rc` < `1.0.0`).
- Identifiers compare per spec — numeric ones numerically, ranking below
  alphanumeric ones. `rc.10` is newer than `rc.9`, which a string comparison
  gets backwards.
- Cargo only selects a pre-release when a comparator opts in at the same
  `major.minor.patch`: `^21.7.0` does **not** match `22.0.0-rc.1`, but
  `^22.0.0-rc.1` matches `22.0.0-rc.2`.
- Build metadata (`+deadbeef`) is dropped — SemVer gives it no precedence.

This matters because soroban-sdk ships real release candidates.

### Fail-silent on uncertainty

Returns no finding, rather than guessing, for: git and path dependencies (no
version to verify), requirement forms the parser does not cover, and malformed
manifests. `github_fetch.py` fetches arbitrary public repos, so one broken
manifest must not fail a scan or invent a finding. A false "your dependencies
drifted" costs more trust than a missed edge case.

### Smaller fixes

- File paths are sorted, so results do not depend on dict iteration order.
- Findings point at the real declaration line instead of a hardcoded line 1.
- Moved two in-function `import re` statements to module level.

---

## `backend/tests/test_analyzer.py`

36 new tests. Two parametrized tables cover the comparator matrix — satisfying
and violating cases for caret, `0.x` caret, tilde, exact, wildcard, and ranges —
plus dedicated tests for:

- Workspace inheritance (`{ workspace = true }` → root `[workspace.dependencies]`)
- `[dev-dependencies]` with a `{ version = ..., features = [...] }` table
- Git dependencies and malformed manifests, both yielding no finding
- A lockfile carrying several majors of one crate, where one satisfies
- Reported file and line for both the drift and missing-lock findings
- Pre-release matching, and identifier ordering (`rc.10` > `rc.9`)

---

## Compatibility

The public signature `check_dependency_version_drift(files: dict[str, str])` is
unchanged, so both callers — `app/api/routes/scans.py` and `scan_source_tree` —
are untouched. All 5 original drift tests pass unmodified, including the LOW
missing-`Cargo.lock` advisory.

The finding's `message` text changed (it now names the requirement rather than a
"pinned version"), and `line` is now the real declaration line rather than `1`.
Nothing asserts on those besides the tests.

---

## Not changed

- **Only `soroban-sdk` is inspected.** Widening to every dependency needs a call
  on how many findings one drifted lockfile should produce. Recorded as the
  follow-up in `backend/README.md` and the architecture roadmap.
- **Missing `Cargo.lock` still emits a LOW advisory**, which contradicts issue
  #21's acceptance criteria. Left as-is by your decision.
- **Nothing was committed.**

---

## Environment changes (earlier in the session, not code)

Installed: backend deps into `backend/.venv` (Python 3.13, though the repo pins
3.12.7), frontend deps via `npm ci`, Rust 1.97.1 `windows-gnu` with the
`wasm32v1-none` target, and stellar-cli 27.0.0. `~/.cargo/bin` was appended to
the persistent User PATH.

`cargo test` in `contract/` still fails — the `backtrace` crate needs `as.exe`,
which rustup's bundled mingw does not ship. The wasm build path is unaffected.
See `SESSION_SUMMARY.md` for the full detail.

---

## Verification

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/ -q     # 124 passed
.venv/Scripts/ruff.exe check .                   # All checks passed
.venv/Scripts/black.exe --check .                # 32 files unchanged
```

Against the real workspace:

```
findings: 0
caret 21.7.0 vs 21.7.7      -> True
caret 21.7.0 vs 22.0.0-rc.1 -> False
=22.0.0-rc.3 vs rc.3        -> True
```
