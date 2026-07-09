"""Route tests for /scans/, verifying scan results are persisted."""

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
