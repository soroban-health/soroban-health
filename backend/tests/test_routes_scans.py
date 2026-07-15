"""Route tests for /scans/, verifying scan results are persisted."""

from app.main import app
from app.services.soroban_client import get_soroban_server
from tests.conftest import FakeSorobanServer, _FakeTransactionsPage
from tests.test_rpc import CONTRACT_ID, _Tx, make_fn_call_diagnostic_event_xdr

BAD_SOURCE = """
pub fn bad_unchecked_withdraw(_env: &Env, amount: i128) -> i128 {
    if amount <= 0 {
        panic!("amount must be positive");
    }
    BALANCE - amount
}
"""


def test_run_scan_persists_result_and_updates_contract_summary(client):
    response = client.post(
        "/scans/",
        json={
            "contract_id": "C123",
            "files": {"lib.rs": BAD_SOURCE},
            "test_coverage_pct": 80.0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["contract_id"] == "C123"
    assert len(body["findings"]) == 1
    assert body["findings"][0]["type"] == "bare_panic_used"

    contract_response = client.get("/contracts/C123")
    assert contract_response.status_code == 200
    summary = contract_response.json()
    assert summary["latest_health_score"] == body["health_score"]
    assert summary["last_scanned_at"] == body["scanned_at"]


def test_run_scan_with_no_files_returns_400(client):
    response = client.post("/scans/", json={"contract_id": "C123", "files": {}})
    assert response.status_code == 400


def test_run_scan_uses_tarpaulin_output_to_set_coverage(client):
    response = client.post(
        "/scans/",
        json={
            "contract_id": "C123",
            "files": {"lib.rs": BAD_SOURCE},
            "coverage_tool": "tarpaulin",
            "coverage_output": "Coverage Results:\n90.40% coverage, 113/125 lines covered",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["test_coverage_pct"] == 90.4


def test_run_scan_rejects_unparseable_coverage_output(client):
    response = client.post(
        "/scans/",
        json={
            "contract_id": "C123",
            "files": {"lib.rs": BAD_SOURCE},
            "coverage_tool": "llvm-cov",
            "coverage_output": "not coverage output",
        },
    )
    assert response.status_code == 422
    assert "Unable to parse coverage_output" in response.json()["detail"]


def test_run_scan_includes_onchain_activity_when_available(client):
    tx = _Tx(
        "SUCCESS", [make_fn_call_diagnostic_event_xdr(CONTRACT_ID, "good_log_event")]
    )
    app.dependency_overrides[get_soroban_server] = lambda: FakeSorobanServer(
        pages=[_FakeTransactionsPage([tx])]
    )
    try:
        response = client.post(
            "/scans/",
            json={"contract_id": CONTRACT_ID, "files": {"lib.rs": BAD_SOURCE}},
        )
    finally:
        del app.dependency_overrides[get_soroban_server]

    assert response.status_code == 200
    activity = response.json()["on_chain_activity"]
    assert activity["available"] is True
    assert activity["invocation_count"] == 1
    assert activity["error_rate"] == 0.0


def test_run_scan_degrades_gracefully_when_rpc_unavailable(client):
    class _BrokenServer(FakeSorobanServer):
        def get_latest_ledger(self):
            from stellar_sdk import exceptions as stellar_exceptions

            raise stellar_exceptions.ConnectionError("network unreachable")

    app.dependency_overrides[get_soroban_server] = lambda: _BrokenServer()
    try:
        response = client.post(
            "/scans/",
            json={"contract_id": CONTRACT_ID, "files": {"lib.rs": BAD_SOURCE}},
        )
    finally:
        del app.dependency_overrides[get_soroban_server]

    assert response.status_code == 200
    activity = response.json()["on_chain_activity"]
    assert activity["available"] is False
