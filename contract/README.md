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

## Verification status

This crate builds, and passes `cargo fmt --check`, `cargo test`, and
`cargo clippy -- -D warnings` on every push — see the [CI workflow](../.github/workflows/ci.yml)
and the badge on the root [README](../README.md). It's built against the
`soroban-sdk` 21.7.x testutils API (`#[contract]`, `#[contractimpl]`,
`#[contracttype]`, `#[contracterror]`, `env.storage().persistent()/instance()`,
`extend_ttl`, `env.register_contract`, `Address::generate`), as documented at
[developers.stellar.org](https://developers.stellar.org/docs/build/smart-contracts/overview).

To verify locally:

```bash
rustup target add wasm32v1-none
cargo fmt --check
stellar contract build
cargo test
cargo clippy -- -D warnings
```

## Deploying to testnet

```bash
cargo build --target wasm32-unknown-unknown --release
stellar contract deploy \
  --wasm target/wasm32-unknown-unknown/release/soroban_health_reference.wasm \
  --source-account <YOUR_TESTNET_ACCOUNT> \
  --network testnet
```

Record the resulting contract ID in the main project README once deployed.
