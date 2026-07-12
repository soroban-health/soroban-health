# Soroban Health

Soroban Health scans your contract for the anti-patterns that paid auditors charge $10k to find — for free, before you deploy.

**Try it live:** [soroban-health.vercel.app](https://soroban-health.vercel.app)

[![CI](https://github.com/soroban-health/soroban-health/actions/workflows/ci.yml/badge.svg)](https://github.com/soroban-health/soroban-health/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Network: Soroban Testnet](https://img.shields.io/badge/network-testnet-orange)](https://developers.stellar.org/docs/networks)

## Why this exists

You ship a contract, it passes every test you wrote, and it works — until a bare `panic!` with no error code takes down a call in production, or a storage entry you forgot to re-extend the TTL on quietly expires and starts throwing errors on read. None of this shows up in local testing. Soroban's WASM/Rust execution model has failure modes that don't exist in a typical backend, and the only way most teams find out about them today is a paid audit — Veridise, Certora, Runtime Verification's Komet — which cost real money, take weeks to schedule, and are out of reach if you're pre-revenue or shipping solo.

Soroban Health is the check you run before that: point it at a contract, get a score and the exact file/line list of what to fix.

## Who uses this

- Teams shipping Soroban contracts who want a fast first-pass check before requesting an audit
- Developers building on Stellar who don't have an audit budget yet
- Maintainers who want to enforce contract hygiene across contributors via CI

## What it catches

- **Unbounded storage growth** → rent costs climb silently and you hit resource limits before anyone notices
- **Bare `panic!`** → callers get an opaque trap instead of a typed error they can actually match on and handle
- **Missing TTL extension** → the entry expires and archives without warning, and reads start failing days or weeks later

## What it does

1. **Scans the Rust source you paste in** for the anti-patterns above, using a real `tree-sitter-rust` AST parse — not a regex guess.
2. **Combines findings with test coverage** into a single 0–100 health score, weighted by severity.
3. **Persists every scan** so you can see whether a contract's score is improving or regressing over time.
4. **Shows all of it in a dashboard** — score, findings with file/line references, and the history chart.

The reference contract in `contract/` ships both the *correct* and *anti-pattern* version of each check, so the scanner has a known-good fixture to test against, and so you can see exactly what "bad" looks like next to "good" in real code.

## Architecture

```
                    ┌─────────────────────┐
                    │   Soroban Testnet /  │
                    │   Mainnet (RPC)       │
                    └──────────┬───────────┘
                               │ events, contract state
                               ▼
┌──────────────┐      ┌─────────────────────┐      ┌──────────────────┐
│   Next.js     │◄────►│   FastAPI Backend    │◄────►│  Supabase         │
│   Frontend    │ REST │   - RPC ingestion     │      │  (Postgres)        │
│   Dashboard   │      │   - Static analysis   │      │  scan history,     │
│               │      │   - Health scoring     │      │  health scores     │
└──────────────┘      └─────────────────────┘      └──────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Reference Contract   │
                    │  (Rust / Soroban SDK)  │
                    │  good + bad patterns   │
                    └─────────────────────┘
```

| Layer | Stack |
|---|---|
| Frontend | Next.js 14, TypeScript, TailwindCSS |
| Backend | Python 3.12, FastAPI |
| Contract | Rust, Soroban SDK |
| Database | Supabase (Postgres) |
| Network | Stellar Soroban (Testnet → Mainnet) |

## Getting started

### Prerequisites
- Node.js 20+
- Python 3.12+
- Rust + `stellar-cli` ([install guide](https://developers.stellar.org/docs/tools/cli))
- A Supabase project (free tier is enough)

### Contract
```bash
cd contract
cargo build --target wasm32-unknown-unknown --release
cargo test
stellar contract deploy \
  --wasm target/wasm32-unknown-unknown/release/soroban_health_reference.wasm \
  --source-account <YOUR_TESTNET_ACCOUNT> \
  --network testnet
```

**Deployed contract ID (testnet):** `CDZ3PQQXOLSPNNDZD4QCXOIBSKZAMTPXNLTEMHVQQNEURGKGG62Z7CAZ`

### Backend
```bash
cd backend
pip install -r requirements.txt --break-system-packages
cp .env.example .env   # fill in SUPABASE_URL, SUPABASE_KEY, SOROBAN_RPC_URL
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env.local   # fill in NEXT_PUBLIC_API_URL
npm run dev
```

Visit `http://localhost:3000`, paste a Soroban contract ID, and run a scan.

## Project status

Early and active. See [open issues](https://github.com/soroban-health/soroban-health/issues) for current scope — many are tagged `good first issue` and sized for a single sitting.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). We use the standard fork → branch → PR flow, and every PR runs through CI (lint + test) before review.

## License

Apache-2.0, see [LICENSE](LICENSE).
