#!/usr/bin/env bash
# Staged commit setup for soroban-health.
#
# This does NOT backdate commits or fake timestamps — that's both
# detectable on GitHub (author vs. committer date) and not the actual
# fix for "this repo looks dumped." What actually matters is genuine,
# logically ordered commits, pushed over real separate days/sessions
# rather than all in one sitting. Run each STAGE as a separate block;
# ideally push after each one and let a day or two pass between groups
# before moving to the next stage.
#
# Usage: review each `git add` list, then run the corresponding
# `git commit`. Don't just blindly run the whole file in one go —
# that defeats the purpose. Suggested real-world pacing is noted
# above each stage.

set -e

git init -b main

# Replace with your actual identity before running.
git config user.name "Chinedu Nwafor"
git config user.email "your-github-email@example.com"

# ─────────────────────────────────────────────────────────────
# STAGE 1 — Project scaffolding & governance (Day 1)
# ─────────────────────────────────────────────────────────────
git add LICENSE CODE_OF_CONDUCT.md .gitignore
git commit -m "chore: add LICENSE, code of conduct, gitignore"

git add README.md docs/architecture.md
git commit -m "docs: add project README and architecture overview"

git add CONTRIBUTING.md .github/
git commit -m "chore: add contributing guide, issue templates, CI workflow"

# ─────────────────────────────────────────────────────────────
# STAGE 2 — Contract (Day 1-2, or a separate day)
# ─────────────────────────────────────────────────────────────
git add contract/Cargo.toml contract/reference/Cargo.toml
git commit -m "feat(contract): scaffold reference contract crate"

git add contract/reference/src/errors.rs
git commit -m "feat(contract): add typed error definitions"

git add contract/reference/src/storage.rs
git commit -m "feat(contract): demonstrate bounded vs unbounded storage growth"

git add contract/reference/src/ttl.rs
git commit -m "feat(contract): demonstrate TTL extension anti-pattern"

git add contract/reference/src/lib.rs
git commit -m "feat(contract): wire up contract entrypoints"

git add contract/reference/src/test.rs
git commit -m "test(contract): add unit tests for good/bad pattern pairs"

git add contract/README.md
git commit -m "docs(contract): document reference contract layout and build steps"

# ─────────────────────────────────────────────────────────────
# STAGE 3 — Backend (Day 2-3)
# ─────────────────────────────────────────────────────────────
git add backend/requirements.txt backend/requirements-dev.txt backend/.env.example
git commit -m "chore(backend): add dependency manifests and env template"

git add backend/app/__init__.py backend/app/core/
git commit -m "feat(backend): add app config"

git add backend/app/models/
git commit -m "feat(backend): add Pydantic models for contracts and scans"

git add backend/app/services/__init__.py backend/app/services/analyzer.py
git commit -m "feat(backend): implement static anti-pattern analyzer"

git add backend/tests/__init__.py backend/tests/test_analyzer.py
git commit -m "test(backend): add analyzer test suite"

git add backend/app/services/scoring.py
git commit -m "feat(backend): implement health scoring formula"

git add backend/tests/test_scoring.py
git commit -m "test(backend): add scoring test suite"

git add backend/app/api/
git commit -m "feat(backend): add contracts, scans, health API routes"

git add backend/app/main.py
git commit -m "feat(backend): wire up FastAPI app entrypoint"

git add backend/README.md
git commit -m "docs(backend): document API endpoints and local dev setup"

# ─────────────────────────────────────────────────────────────
# STAGE 4 — Frontend (Day 3-4)
# ─────────────────────────────────────────────────────────────
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/next.config.js \
        frontend/tailwind.config.js frontend/postcss.config.js \
        frontend/.eslintrc.json frontend/.env.example frontend/next-env.d.ts
git commit -m "chore(frontend): scaffold Next.js project config"

git add frontend/app/globals.css frontend/app/layout.tsx
git commit -m "feat(frontend): add root layout and global styles"

git add frontend/lib/
git commit -m "feat(frontend): add API client and shared types"

git add frontend/components/HealthScoreGauge.tsx
git commit -m "feat(frontend): add health score gauge component"

git add frontend/components/FindingsList.tsx
git commit -m "feat(frontend): add findings list component"

git add frontend/app/page.tsx
git commit -m "feat(frontend): build scan dashboard page"

# ─────────────────────────────────────────────────────────────
# STAGE 5 — Seed issues reference doc (Day 4, before opening real issues)
# ─────────────────────────────────────────────────────────────
git add docs/seed-issues.md
git commit -m "docs: add seed issue list for contributors"

echo ""
echo "Done. Run 'git log --oneline' to review, then:"
echo "  git remote add origin git@github.com:<org>/soroban-health.git"
echo "  git push -u origin main"
