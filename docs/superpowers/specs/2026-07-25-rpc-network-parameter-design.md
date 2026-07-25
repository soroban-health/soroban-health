# RPC Network Parameter Design

Follow-up to the RPC health-signal issue: the on-chain activity fetch
already lives in `backend/app/services/rpc.py` (merged in 93b13c7) with
`invocation_count`/`error_rate` folded into `compute_health_score`. What's
missing is a `network` parameter on the scan request — today a scan always
checks whatever network `Settings.SOROBAN_RPC_URL` points to (testnet by
default), with no per-request override.

## Scope

Small, plumbing-only change. No new RPC endpoints and no per-network
`SorobanServer` selection — there is still only one configured RPC
endpoint. This adds the `network` field to the request shape and makes the
single supported value explicit and validated, rather than silently
ignoring any value the caller might send.

## Changes

- `SorobanActivityService.fetch_activity` gains a `network: str = "testnet"`
  keyword parameter. It validates against a module-level
  `SUPPORTED_NETWORKS = frozenset({"testnet"})`; a `network` not in that
  set raises `RpcUnavailableError` (already caught in `scans.py` and
  turned into a graceful no-penalty fallback — no new exception type
  needed). Passing `"testnet"` (the default) behaves identically to today.
- `ScanSourceRequest` and `ScanRepoRequest` (in `backend/app/api/routes/scans.py`)
  gain `network: str = Field(default="testnet", description="testnet | mainnet — only testnet has a live RPC endpoint configured today")`,
  matching the existing convention in `models/contract.py`.
- `_scan_and_persist` accepts `network` and passes it through to
  `onchain.fetch_activity(contract_id, network=network)`.
- Both route handlers (`run_scan`, `run_repo_scan`) pass `payload.network`
  through to `_scan_and_persist`.

## Testing

- Unit test: `fetch_activity(contract_id, network="testnet")` behaves as
  before (existing tests already cover this via the default).
- New test: `fetch_activity(contract_id, network="mainnet")` raises
  `RpcUnavailableError`.
- New test: a scan request with `network="mainnet"` still returns a
  `ScanResult` with `on_chain_activity.available == False` and a `reason`
  mentioning the network, rather than failing the whole scan.

## Out of Scope

- Actually wiring a second RPC endpoint/passphrase for mainnet.
- Any per-network config surface in `Settings` beyond documenting that
  only testnet is live.
