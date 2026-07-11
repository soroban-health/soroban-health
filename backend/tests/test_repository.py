"""Tests for ContractRepository against the fake Supabase client double."""

from app.models.contract import ContractRegisterRequest
from app.models.scan import Finding, FindingType, ScanResult, Severity
from app.services.repository import ContractRepository

VALID_CONTRACT_ID_1 = "CAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
VALID_CONTRACT_ID_2 = "CBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"


def test_register_contract_creates_row(fake_client):
    repo = ContractRepository(fake_client)
    summary = repo.register_contract(
        ContractRegisterRequest(
            contract_id=VALID_CONTRACT_ID_1,
            network="testnet",
            label="Demo",
        )
    )
    assert summary.contract_id == VALID_CONTRACT_ID_1
    assert summary.network == "testnet"
    assert summary.label == "Demo"
    assert summary.latest_health_score is None
    assert summary.last_scanned_at is None


def test_get_contract_returns_none_when_missing(fake_client):
    repo = ContractRepository(fake_client)
    assert repo.get_contract("does-not-exist") is None


def test_get_contract_returns_registered_contract(fake_client):
    repo = ContractRepository(fake_client)
    repo.register_contract(ContractRegisterRequest(contract_id=VALID_CONTRACT_ID_1))
    summary = repo.get_contract(VALID_CONTRACT_ID_1)
    assert summary is not None
    assert summary.contract_id == VALID_CONTRACT_ID_1


def test_list_contracts_returns_all(fake_client):
    repo = ContractRepository(fake_client)
    repo.register_contract(ContractRegisterRequest(contract_id=VALID_CONTRACT_ID_1))
    repo.register_contract(ContractRegisterRequest(contract_id=VALID_CONTRACT_ID_2))
    contract_ids = {summary.contract_id for summary in repo.list_contracts()}
    assert contract_ids == {VALID_CONTRACT_ID_1, VALID_CONTRACT_ID_2}


def _scan_result(
    contract_id: str,
    findings: list[Finding] | None = None,
    health_score: float = 87.5,
    scanned_at: str = "2026-07-07T00:00:00+00:00",
) -> ScanResult:
    return ScanResult(
        contract_id=contract_id,
        health_score=health_score,
        test_coverage_pct=90.0,
        findings=findings or [],
        scanned_at=scanned_at,
    )


def test_record_scan_persists_scan_and_findings_and_updates_contract_summary(
    fake_client,
):
    repo = ContractRepository(fake_client)
    repo.register_contract(
        ContractRegisterRequest(contract_id=VALID_CONTRACT_ID_1, label="Demo")
    )

    finding = Finding(
        type=FindingType.BARE_PANIC_USED,
        severity=Severity.HIGH,
        file="lib.rs",
        line=12,
        message="bare panic! used",
    )
    repo.record_scan(_scan_result(VALID_CONTRACT_ID_1, findings=[finding]))

    summary = repo.get_contract(VALID_CONTRACT_ID_1)
    assert summary is not None
    assert summary.latest_health_score == 87.5
    assert summary.last_scanned_at == "2026-07-07T00:00:00+00:00"
    # Registration-time fields are preserved by the upsert, not clobbered.
    assert summary.label == "Demo"

    scans = fake_client._store["scans"]
    assert len(scans) == 1
    assert scans[0]["contract_id"] == VALID_CONTRACT_ID_1

    findings_rows = fake_client._store["findings"]
    assert len(findings_rows) == 1
    assert findings_rows[0]["scan_id"] == scans[0]["id"]
    assert findings_rows[0]["type"] == "bare_panic_used"
    assert findings_rows[0]["severity"] == "high"


def test_record_scan_auto_vivifies_unregistered_contract(fake_client):
    repo = ContractRepository(fake_client)
    repo.record_scan(_scan_result("C-never-registered"))

    summary = repo.get_contract("C-never-registered")
    assert summary is not None
    assert summary.latest_health_score == 87.5


def test_record_scan_skips_findings_insert_when_none(fake_client):
    repo = ContractRepository(fake_client)
    repo.record_scan(_scan_result(VALID_CONTRACT_ID_1))
    assert fake_client._store.get("findings", []) == []


def test_list_scan_history_returns_ascending_order_regardless_of_insert_order(
    fake_client,
):
    repo = ContractRepository(fake_client)
    repo.record_scan(
        _scan_result(
            VALID_CONTRACT_ID_1,
            health_score=90.0,
            scanned_at="2026-07-08T00:00:00+00:00",
        )
    )
    repo.record_scan(
        _scan_result(
            VALID_CONTRACT_ID_1,
            health_score=70.0,
            scanned_at="2026-07-05T00:00:00+00:00",
        )
    )
    repo.record_scan(
        _scan_result(
            VALID_CONTRACT_ID_1,
            health_score=80.0,
            scanned_at="2026-07-06T00:00:00+00:00",
        )
    )

    history = repo.list_scan_history(VALID_CONTRACT_ID_1)
    assert [entry.scanned_at for entry in history] == [
        "2026-07-05T00:00:00+00:00",
        "2026-07-06T00:00:00+00:00",
        "2026-07-08T00:00:00+00:00",
    ]
    assert [entry.health_score for entry in history] == [70.0, 80.0, 90.0]


def test_list_scan_history_returns_empty_when_no_scans(fake_client):
    repo = ContractRepository(fake_client)
    assert repo.list_scan_history("C-never-scanned") == []
