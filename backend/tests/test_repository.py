"""Tests for ContractRepository against the fake Supabase client double."""

from app.models.contract import ContractRegisterRequest
from app.models.scan import Finding, FindingType, ScanResult, Severity
from app.services.repository import ContractRepository


def test_register_contract_creates_row(fake_client):
    repo = ContractRepository(fake_client)
    summary = repo.register_contract(
        ContractRegisterRequest(contract_id="C123", network="testnet", label="Demo")
    )
    assert summary.contract_id == "C123"
    assert summary.network == "testnet"
    assert summary.label == "Demo"
    assert summary.latest_health_score is None
    assert summary.last_scanned_at is None


def test_get_contract_returns_none_when_missing(fake_client):
    repo = ContractRepository(fake_client)
    assert repo.get_contract("does-not-exist") is None


def test_get_contract_returns_registered_contract(fake_client):
    repo = ContractRepository(fake_client)
    repo.register_contract(ContractRegisterRequest(contract_id="C123"))
    summary = repo.get_contract("C123")
    assert summary is not None
    assert summary.contract_id == "C123"


def test_list_contracts_returns_all(fake_client):
    repo = ContractRepository(fake_client)
    repo.register_contract(ContractRegisterRequest(contract_id="C1"))
    repo.register_contract(ContractRegisterRequest(contract_id="C2"))
    contract_ids = {summary.contract_id for summary in repo.list_contracts()}
    assert contract_ids == {"C1", "C2"}


def _scan_result(contract_id: str, findings: list[Finding] | None = None) -> ScanResult:
    return ScanResult(
        contract_id=contract_id,
        health_score=87.5,
        test_coverage_pct=90.0,
        findings=findings or [],
        scanned_at="2026-07-07T00:00:00+00:00",
    )


def test_record_scan_persists_scan_and_findings_and_updates_contract_summary(
    fake_client,
):
    repo = ContractRepository(fake_client)
    repo.register_contract(ContractRegisterRequest(contract_id="C123", label="Demo"))

    finding = Finding(
        type=FindingType.BARE_PANIC_USED,
        severity=Severity.HIGH,
        file="lib.rs",
        line=12,
        message="bare panic! used",
    )
    repo.record_scan(_scan_result("C123", findings=[finding]))

    summary = repo.get_contract("C123")
    assert summary is not None
    assert summary.latest_health_score == 87.5
    assert summary.last_scanned_at == "2026-07-07T00:00:00+00:00"
    # Registration-time fields are preserved by the upsert, not clobbered.
    assert summary.label == "Demo"

    scans = fake_client._store["scans"]
    assert len(scans) == 1
    assert scans[0]["contract_id"] == "C123"

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
    repo.record_scan(_scan_result("C123"))
    assert fake_client._store.get("findings", []) == []
