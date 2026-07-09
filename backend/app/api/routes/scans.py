"""Routes for triggering and retrieving contract scans."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_repository
from app.models.scan import Finding, ScanResult, Severity
from app.services.repository import ContractRepository
from app.services.scoring import compute_health_score

router = APIRouter()

# Severity weights used when computing the health score from findings.
_SEVERITY_PENALTY = {
    Severity.LOW: 2,
    Severity.MEDIUM: 5,
    Severity.HIGH: 12,
}


class ScanSourceRequest(BaseModel):
    """For now, scanning takes already-fetched source text rather than
    cloning a repo server-side. Issue #TBD tracks adding a `repo_url`
    variant that clones and scans automatically — kept out of v0 so the
    API surface doesn't grow ahead of what's actually been built and
    tested.
    """

    contract_id: str
    files: dict[str, str]  # relative path -> file contents
    test_coverage_pct: float | None = None


@router.post("/", response_model=ScanResult)
async def run_scan(
    payload: ScanSourceRequest,
    repo: ContractRepository = Depends(get_repository),
) -> ScanResult:
    if not payload.files:
        raise HTTPException(status_code=400, detail="No files provided to scan")

    from app.services.analyzer import scan_file, check_dependency_version_drift

    findings: list[Finding] = []
    
    # Run per-file checks
    for path, source in payload.files.items():
        if path.endswith(".rs"):
            findings.extend(scan_file(path, source))
            
    # Run cross-file checks
    findings.extend(check_dependency_version_drift(payload.files))

    score = compute_health_score(
        findings=findings,
        test_coverage_pct=payload.test_coverage_pct,
        severity_penalty=_SEVERITY_PENALTY,
    )

    result = ScanResult(
        contract_id=payload.contract_id,
        health_score=score,
        test_coverage_pct=payload.test_coverage_pct,
        findings=findings,
        scanned_at=datetime.now(timezone.utc).isoformat(),
    )
    await run_in_threadpool(repo.record_scan, result)
    return result
