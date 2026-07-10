"""Routes for triggering and retrieving contract scans."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_repository
from app.models.scan import Finding, ScanResult, Severity
from app.services.coverage import CoverageTool, parse_coverage_pct
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
    test_coverage_pct: float | None = Field(default=None, ge=0, le=100)
    coverage_output: str | None = Field(
        default=None,
        description=(
            "Raw output from cargo tarpaulin or cargo llvm-cov. "
            "Used to derive test coverage automatically when test_coverage_pct is omitted."
        ),
    )
    coverage_tool: CoverageTool = CoverageTool.AUTO


@router.post("/", response_model=ScanResult)
async def run_scan(
    payload: ScanSourceRequest,
    repo: ContractRepository = Depends(get_repository),
) -> ScanResult:
    if not payload.files:
        raise HTTPException(status_code=400, detail="No files provided to scan")

    test_coverage_pct = payload.test_coverage_pct
    if test_coverage_pct is None and payload.coverage_output:
        test_coverage_pct = parse_coverage_pct(
            output=payload.coverage_output,
            tool=payload.coverage_tool,
        )
        if test_coverage_pct is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Unable to parse coverage_output. Provide cargo tarpaulin/cargo llvm-cov output "
                    "or set test_coverage_pct explicitly."
                ),
            )

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
        test_coverage_pct=test_coverage_pct,
        severity_penalty=_SEVERITY_PENALTY,
    )

    result = ScanResult(
        contract_id=payload.contract_id,
        health_score=score,
        test_coverage_pct=test_coverage_pct,
        findings=findings,
        scanned_at=datetime.now(timezone.utc).isoformat(),
    )
    await run_in_threadpool(repo.record_scan, result)
    return result
