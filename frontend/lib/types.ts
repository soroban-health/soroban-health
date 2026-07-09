// Mirrors backend/app/models/{contract,scan}.py — keep these in sync
// manually for now; generating from the FastAPI OpenAPI schema is a
// good "medium" complexity issue for anyone picking this repo up.

export type Severity = "low" | "medium" | "high";

export type FindingType =
  | "unbounded_storage_growth"
  | "bare_panic_used"
  | "missing_ttl_extension"
  | "dependency_version_drift";

export interface Finding {
  type: FindingType;
  severity: Severity;
  file: string;
  line: number;
  message: string;
}

export interface ScanResult {
  contract_id: string;
  health_score: number;
  test_coverage_pct: number | null;
  findings: Finding[];
  scanned_at: string;
}

export interface ContractSummary {
  contract_id: string;
  network: string;
  label: string | null;
  latest_health_score: number | null;
  last_scanned_at: string | null;
}

export interface ScanHistoryEntry {
  health_score: number;
  scanned_at: string;
}
