# Reference contract

The reference contract (`contract/reference/`) is a Soroban Health test
fixture: each anti-pattern the scanner checks for has a paired `good_*` /
`bad_*` method, so the scanner can be tested against known-correct and
known-bad code side by side. It is not a product contract.

- **Network:** Stellar Testnet
- **Contract ID:** `CDZ3PQQXOLSPNNDZD4QCXOIBSKZAMTPXNLTEMHVQQNEURGKGG62Z7CAZ`
- **Explorer:** [stellar.expert/explorer/testnet/contract/CDZ3PQQXOLSPNNDZD4QCXOIBSKZAMTPXNLTEMHVQQNEURGKGG62Z7CAZ](https://stellar.expert/explorer/testnet/contract/CDZ3PQQXOLSPNNDZD4QCXOIBSKZAMTPXNLTEMHVQQNEURGKGG62Z7CAZ)

## Building and deploying

```bash
cd contract
cargo build --target wasm32-unknown-unknown --release
cargo test
stellar contract deploy \
  --wasm target/wasm32-unknown-unknown/release/soroban_health_reference.wasm \
  --source-account <YOUR_TESTNET_ACCOUNT> \
  --network testnet
```

## Invoking it

```bash
stellar contract invoke \
  --id CDZ3PQQXOLSPNNDZD4QCXOIBSKZAMTPXNLTEMHVQQNEURGKGG62Z7CAZ \
  --source-account <YOUR_TESTNET_ACCOUNT> \
  --network testnet \
  -- \
  <method> [args...]
```

Substitute `<method>` and its arguments from the table below — for example:

```bash
stellar contract invoke \
  --id CDZ3PQQXOLSPNNDZD4QCXOIBSKZAMTPXNLTEMHVQQNEURGKGG62Z7CAZ \
  --source-account <YOUR_TESTNET_ACCOUNT> \
  --network testnet \
  -- \
  initialize --admin <ADMIN_ADDRESS>
```

## Public methods

| Method | Does |
|---|---|
| `initialize(admin)` | One-time setup — stores the given address as the contract administrator. |
| `good_log_event(label)` | Appends `label` to a bounded log, evicting the oldest entry once the cap is reached. |
| `bad_log_event(label)` | Appends `label` to a log with no cap, so storage grows without bound as the contract is used. |
| `good_withdraw(amount)` | Validates `amount` and returns a typed `Result<i128, HealthError>`, so callers can match on the specific failure. |
| `bad_withdraw(amount)` | Validates `amount` with a bare `panic!`, which produces an opaque failure with no error code. |
| `good_persist_record(key, value)` | Writes `value` to persistent storage under `key` and immediately extends its TTL. |
| `bad_persist_record(key, value)` | Writes `value` to persistent storage under `key` without extending its TTL, so the entry eventually expires. |
