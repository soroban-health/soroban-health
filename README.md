# Soroban Health

> Contract observability, anti-pattern detection, and test-coverage scoring for Soroban smart contracts on Stellar.

[![CI](https://github.com/soroban-health/soroban-health/actions/workflows/ci.yml/badge.svg)](https://github.com/soroban-health/soroban-health/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Network: Soroban Testnet](https://img.shields.io/badge/network-testnet-orange)](https://developers.stellar.org/docs/networks)

## The problem

Soroban gives developers a fast, cheap way to ship smart contracts on Stellar — but the WASM/Rust execution model introduces failure modes that don't exist in traditional backend code, and that most teams only discover during a paid audit, if at all:

- **Unbounded storage growth** that silently inflates rent costs or hits resource limits in production
- **`panic!` used instead of `panic_with_error!`**, which produces opaque failures instead of typed, debuggable errors
- **Missing TTL (time-to-live) extension** on persistent/temporary storage entries, causing data to expire unexpectedly
- **Untracked dependency drift** between local dev environments and what's actually deployed on-chain
- Thin or absent test coverage that isn't visible anywhere until something breaks

Paid audits (Veridise, Certora, Runtime Verification's Komet) catch these, but they're expensive, infrequent, and out of reach for early-stage or solo builders — which describes a large share of the ~100+ projects building on Soroban today. Soroban Health is a free, open-source, self-serve first line of defense: point it at a contract, get a health score and a concrete list of what to fix before you ever need an auditor.

## What it does

1. **Connects to any deployed Soroban contract** (testnet or mainnet) via Soroban RPC and pulls its on-chain event history.
2. **Scans the contract's Rust source** for the known anti-patterns above using lightweight static analysis.
3. **Computes a Health Score** combining: test coverage, anti-pattern findings (weighted by severity), and on-chain activity signals (invocation frequency, error rate).
4. **Surfaces everything in a live dashboard** — per-contract health, a timeline of on-chain events, and a diffable list of findings with file/line references.

Soroban Health ships with a small **reference contract** (`contract/`) that intentionally implements both the *correct* and *anti-pattern* version of each check, so the scanner has a known-good fixture to validate against and so other contributors can see exactly what "bad" looks like in context.

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
