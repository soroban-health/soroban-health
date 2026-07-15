"""Tests for SorobanActivityService against the fake Soroban RPC client.

`make_fn_call_diagnostic_event_xdr` builds a real `fn_call`
`DiagnosticEvent` XDR string via `stellar_sdk.xdr` directly (not a mock),
so `_invokes_contract`'s actual decode path is exercised in these tests,
not bypassed.
"""

from stellar_sdk import xdr as stellar_xdr
from stellar_sdk.strkey import StrKey

from app.services.rpc import RpcUnavailableError, SorobanActivityService
from tests.conftest import FakeSorobanServer, _FakeTransactionsPage

CONTRACT_ID = "CDZ3PQQXOLSPNNDZD4QCXOIBSKZAMTPXNLTEMHVQQNEURGKGG62Z7CAZ"
OTHER_CONTRACT_ID = "CCWA6IAGJASTLSRJKNGM6NTDAIK7EAA66PKSWHFLARQKKCYUE6KZHPRY"


def make_fn_call_diagnostic_event_xdr(contract_id: str, function_name: str) -> str:
    contract_bytes = StrKey.decode_contract(contract_id)
    topics = [
        stellar_xdr.SCVal(
            stellar_xdr.SCValType.SCV_SYMBOL, sym=stellar_xdr.SCSymbol(b"fn_call")
        ),
        stellar_xdr.SCVal(
            stellar_xdr.SCValType.SCV_BYTES, bytes=stellar_xdr.SCBytes(contract_bytes)
        ),
        stellar_xdr.SCVal(
            stellar_xdr.SCValType.SCV_SYMBOL,
            sym=stellar_xdr.SCSymbol(function_name.encode()),
        ),
    ]
    body = stellar_xdr.ContractEventBody(
        v=0,
        v0=stellar_xdr.ContractEventV0(
            topics=topics, data=stellar_xdr.SCVal(stellar_xdr.SCValType.SCV_VOID)
        ),
    )
    event = stellar_xdr.ContractEvent(
        ext=stellar_xdr.ExtensionPoint(0),
        contract_id=None,
        type=stellar_xdr.ContractEventType.CONTRACT,
        body=body,
    )
    return stellar_xdr.DiagnosticEvent(
        in_successful_contract_call=True, event=event
    ).to_xdr()


class _Tx:
    def __init__(
        self,
        status: str,
        diagnostic_events_xdr: list[str] | None = None,
        ledger: int = 1,
    ) -> None:
        self.status = status
        self.diagnostic_events_xdr = diagnostic_events_xdr or []
        self.ledger = ledger


def test_fetch_activity_reports_not_deployed(monkeypatch):
    server = FakeSorobanServer(deployed=False)
    service = SorobanActivityService(server)
    activity = service.fetch_activity(CONTRACT_ID)
    assert activity.available is False
    assert activity.reason == "not deployed to this network"


def test_fetch_activity_counts_matching_invocations_and_errors():
    matching_ok = _Tx(
        "SUCCESS", [make_fn_call_diagnostic_event_xdr(CONTRACT_ID, "good_log_event")]
    )
    matching_failed = _Tx(
        "FAILED", [make_fn_call_diagnostic_event_xdr(CONTRACT_ID, "bad_withdraw")]
    )
    unrelated = _Tx(
        "SUCCESS", [make_fn_call_diagnostic_event_xdr(OTHER_CONTRACT_ID, "hello")]
    )
    no_diagnostics = _Tx("SUCCESS", [])

    server = FakeSorobanServer(
        pages=[
            _FakeTransactionsPage(
                [matching_ok, matching_failed, unrelated, no_diagnostics], cursor="c1"
            )
        ]
    )
    service = SorobanActivityService(server)
    activity = service.fetch_activity(CONTRACT_ID)

    assert activity.available is True
    assert activity.invocation_count == 2
    assert activity.error_count == 1
    assert activity.error_rate == 0.5


def test_fetch_activity_returns_zero_invocations_when_idle():
    server = FakeSorobanServer(pages=[_FakeTransactionsPage([])])
    service = SorobanActivityService(server)
    activity = service.fetch_activity(CONTRACT_ID)

    assert activity.available is True
    assert activity.invocation_count == 0
    assert activity.error_rate == 0.0


def test_fetch_activity_stops_at_max_pages():
    page = _FakeTransactionsPage(
        [_Tx("SUCCESS", [make_fn_call_diagnostic_event_xdr(CONTRACT_ID, "x")])] * 200,
        cursor="next",
    )
    # 10 full pages available, but max_pages=2 should stop early.
    server = FakeSorobanServer(pages=[page] * 10)
    service = SorobanActivityService(server)
    activity = service.fetch_activity(CONTRACT_ID, max_pages=2, page_limit=200)

    assert activity.invocation_count == 400


def test_fetch_activity_wraps_unexpected_errors(monkeypatch):
    class _BrokenServer(FakeSorobanServer):
        def get_latest_ledger(self):
            from stellar_sdk import exceptions as stellar_exceptions

            raise stellar_exceptions.ConnectionError("network unreachable")

    service = SorobanActivityService(_BrokenServer())
    try:
        service.fetch_activity(CONTRACT_ID)
        assert False, "expected RpcUnavailableError"
    except RpcUnavailableError:
        pass
