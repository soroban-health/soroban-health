"""Pydantic models for scan results and findings."""

from enum import Enum

from pydantic import BaseModel, Field


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
    on_chain_activity: OnChainActivity | None = None
    scanned_at: str


class ScanHistoryEntry(BaseModel):
    health_score: float = Field(..., ge=0, le=100)
    scanned_at: str
