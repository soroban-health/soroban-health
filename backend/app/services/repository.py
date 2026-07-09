"""Supabase-backed persistence for tracked contracts and scan results."""

from supabase import Client

from app.models.contract import ContractRegisterRequest, ContractSummary
from app.models.scan import ScanResult


class ContractRepository:
    def __init__(self, client: Client) -> None:
        self._client = client

    def register_contract(self, payload: ContractRegisterRequest) -> ContractSummary:
        response = (
            self._client.table("contracts")
            .insert(
                {
                    "contract_id": payload.contract_id,
                    "network": payload.network,
                    "label": payload.label,
                }
            )
            .execute()
        )
        return ContractSummary(**response.data[0])

    def get_contract(self, contract_id: str) -> ContractSummary | None:
        response = (
            self._client.table("contracts")
            .select("*")
            .eq("contract_id", contract_id)
            .execute()
        )
        if not response.data:
            return None
        return ContractSummary(**response.data[0])

    def list_contracts(self) -> list[ContractSummary]:
        response = self._client.table("contracts").select("*").execute()
        return [ContractSummary(**row) for row in response.data]

    def record_scan(self, result: ScanResult) -> None:
        # Upsert the contract row first (auto-vivifying one if this
        # contract_id was never registered via POST /contracts/, matching
        # the endpoint's existing permissive behavior) so the scans FK
        # below is always satisfied. `on_conflict` merges only the columns
        # given here, leaving an existing row's network/label untouched.
        self._client.table("contracts").upsert(
            {
                "contract_id": result.contract_id,
                "latest_health_score": result.health_score,
                "last_scanned_at": result.scanned_at,
            },
            on_conflict="contract_id",
        ).execute()

        scan_response = (
            self._client.table("scans")
            .insert(
                {
                    "contract_id": result.contract_id,
                    "health_score": result.health_score,
                    "test_coverage_pct": result.test_coverage_pct,
                    "scanned_at": result.scanned_at,
                }
            )
            .execute()
        )
        scan_id = scan_response.data[0]["id"]

        if result.findings:
            self._client.table("findings").insert(
                [
                    {
                        "scan_id": scan_id,
                        "type": finding.type.value,
                        "severity": finding.severity.value,
                        "file": finding.file,
                        "line": finding.line,
                        "message": finding.message,
                    }
                    for finding in result.findings
                ]
            ).execute()
