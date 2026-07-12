# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Redesigned the dashboard UI: dark terminal aesthetic, animated health-score
  gauge with a red → amber → green color sweep, code-editor-style scan form
- Rewrote the README and architecture docs for a practitioner-facing tone

### Fixed
- Backend deploy pinned to Python 3.12 for Render (was defaulting to the
  latest Python, breaking the build for Rust-backed dependencies)
- Committed `contract/Cargo.lock`, which was previously gitignored and let
  dependency resolution drift silently over time
- Backend formatting (black) applied to files that had been merged
  unformatted, which was failing CI's format-check step

### Removed
- Internal `git-stage-setup.sh` scaffolding script
- `docs/seed-issues.md` (internal issue-drafting notes)

### Planned
- Live Soroban RPC event ingestion

## [0.2.0] - 2026-07-11

### Added
- Dependency version drift check (flags a `Cargo.toml`/`Cargo.lock`
  `soroban-sdk` version mismatch)
- Loading skeleton on the scan results view
- Supabase persistence for tracked contracts and scan history
- Contract health history chart on the dashboard
- Contract ID format validation (56-char, C-prefix check)
- Automatic test coverage parsing (`cargo tarpaulin` / `cargo llvm-cov` output)

### Changed
- Static analyzer rewritten from regex/line-window heuristics to
  `tree-sitter-rust` AST parsing

### Fixed
- CI workflow updated to use the `wasm32v1-none` target via
  `stellar contract build`
- Reference contract test suite updated to the soroban-sdk 21.7 testutils API

## [0.1.0] - 2026-06-30

### Added
- Reference Soroban contract demonstrating 3 anti-pattern pairs (storage,
  errors, TTL)
- FastAPI static analysis backend with regex-based pattern detection
- Health scoring formula (0-100) combining findings and coverage data
- Next.js dashboard with animated health score gauge
- Deployed to Stellar testnet:
  `CDZ3PQQXOLSPNNDZD4QCXOIBSKZAMTPXNLTEMHVQQNEURGKGG62Z7CAZ`
- Full CI pipeline (Rust + Python + TypeScript)
