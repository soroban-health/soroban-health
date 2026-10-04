"""Pydantic models for scan results and findings."""

from enum import Enum

from typing import Any
from pydantic import BaseModel, Field, model_validator


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FindingType(str, Enum):
    UNBOUNDED_STORAGE_GROWTH = "unbounded_storage_growth"
    BARE_PANIC_USED = "bare_panic_used"
    MISSING_TTL_EXTENSION = "missing_ttl_extension"
    DEPENDENCY_VERSION_DRIFT = "dependency_version_drift"


class Finding(BaseModel):
    type: FindingType
    severity: Severity
    file: str
    line: int
    message: str


class OnChainActivity(BaseModel):
    """Result of SorobanActivityService.fetch_activity (see
    app/services/rpc.py). `available` distinguishes "checked, nothing to
    report" (a deployed but idle contract) from "couldn't check" (RPC
    unreachable, or the contract isn't deployed to the configured
    network) — the latter carries `reason` and never affects
    health_score, the same way missing on-chain history is treated as
    unknown rather than suspicious.
    """

    available: bool
    ledgers_scanned_from: int | None = None
    ledgers_scanned_to: int | None = None
    invocation_count: int = 0
    error_count: int = 0
    error_rate: float | None = None
    reason: str | None = None


class ScanResult(BaseModel):
    contract_id: str
    health_score: float = Field(..., ge=0, le=100)
    test_coverage_pct: float | None = Field(default=None, ge=0, le=100)
    findings: list[Finding] = []
    findings_summary: dict[str, int] = Field(
        default_factory=lambda: {"high": 0, "medium": 0, "low": 0}
    )
    on_chain_activity: OnChainActivity | None = None
    scanned_at: str

    @model_validator(mode="before")
    @classmethod
    def populate_findings_summary(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "findings_summary" not in data or not data["findings_summary"]:
                findings = data.get("findings", [])
                summary = {"high": 0, "medium": 0, "low": 0}
                for f in findings:
                    sev = f.get("severity") if isinstance(f, dict) else getattr(f, "severity", None)
                    sev_str = sev.value if hasattr(sev, "value") else str(sev).lower()
                    if sev_str in summary:
                        summary[sev_str] += 1
                data["findings_summary"] = summary
        return data


class ScanHistoryEntry(BaseModel):
    health_score: float = Field(..., ge=0, le=100)
    scanned_at: str
