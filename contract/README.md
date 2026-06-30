# Soroban Health — Reference Contract

This crate is a **fixture, not a product contract**. It exists purely so the
Soroban Health scanner has known-good and known-bad code to validate against.

## Layout

| File | Demonstrates |
|---|---|
| `src/storage.rs` | Bounded vs. unbounded storage growth |
| `src/errors.rs` | Typed errors (`Result<_, ContractError>`) vs. bare `panic!` |
| `src/ttl.rs` | Correct `extend_ttl` usage vs. missing TTL extension |
| `src/test.rs` | Unit tests covering both the good and bad path of each pair |
| `src/lib.rs` | Contract entrypoint wiring the above together |

Every "bad" function has an inline comment explaining exactly what the
scanner should flag and why it's a real-world risk, not just a style nit.

## ⚠️ Build verification status

This crate was written against the public `soroban-sdk` 21.x API
(`#[contract]`, `#[contractimpl]`, `#[contracttype]`, `#[contracterror]`,
`env.storage().persistent()/instance()`, `extend_ttl`, `Env::register`,
`Address::generate` in testutils) as documented at
[developers.stellar.org](https://developers.stellar.org/docs/build/smart-contracts/overview).

**It has not yet been compiled or run in a sandboxed environment with
network access to crates.io / rustup**, so treat it as a careful first
draft rather than a verified build. Before your first commit, run:

```bash
rustup target add wasm32-unknown-unknown
cargo build --target wasm32-unknown-unknown --release
cargo test
cargo clippy --target wasm32-unknown-unknown -- -D warnings
```

and fix anything the compiler flags — SDK minor-version API drift (e.g.
exact `register` / testutils signatures) is the most likely source of
small mismatches. Once it builds and tests pass locally, this note
should be deleted before your first public push, since a reviewer
seeing "not yet verified" in the repo undercuts the project's credibility.

## Deploying to testnet

```bash
cargo build --target wasm32-unknown-unknown --release
stellar contract deploy \
  --wasm target/wasm32-unknown-unknown/release/soroban_health_reference.wasm \
  --source-account <YOUR_TESTNET_ACCOUNT> \
  --network testnet
```

Record the resulting contract ID in the main project README once deployed.
