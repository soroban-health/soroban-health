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


class ScanResult(BaseModel):
    contract_id: str
    health_score: float = Field(..., ge=0, le=100)
    test_coverage_pct: float | None = Field(default=None, ge=0, le=100)
    findings: list[Finding] = []
    scanned_at: str


class ScanHistoryEntry(BaseModel):
    health_score: float = Field(..., ge=0, le=100)
    scanned_at: str
