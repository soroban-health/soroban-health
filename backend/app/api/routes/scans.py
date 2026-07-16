"""Routes for triggering and retrieving contract scans."""

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_github_client, get_onchain_service, get_repository
from app.models.scan import Finding, OnChainActivity, ScanResult, Severity
from app.services.analyzer import check_dependency_version_drift, scan_file
from app.services.coverage import CoverageTool, parse_coverage_pct
from app.services.github_fetch import (
    GitHubFetchError,
    InvalidRepoUrlError,
    NoScannableFilesError,
    RepoFetchTimeoutError,
    RepoNotFoundError,
    RepoTooLargeError,
    TooManyFilesError,
    fetch_repo_files,
    parse_github_repo_url,
)
from app.services.repository import ContractRepository
from app.services.rpc import RpcUnavailableError, SorobanActivityService
from app.services.scoring import compute_health_score

router = APIRouter()

# Severity weights used when computing the health score from findings.
_SEVERITY_PENALTY = {
    Severity.LOW: 2,
    Severity.MEDIUM: 5,
    Severity.HIGH: 12,
}


class ScanSourceRequest(BaseModel):
    """Runs a scan against already-fetched source text. `POST /scans/repo`
    is the alternative entry point: it fetches source directly from a
    public GitHub repo instead of requiring the caller to paste files here.
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


class ScanRepoRequest(BaseModel):
    repo_url: str = Field(
        ...,
        description=(
            "A github.com repo URL, e.g. https://github.com/owner/repo, "
            "optionally with /tree/<branch>"
        ),
    )
    contract_id: str | None = Field(
        default=None,
        description=(
            "Defaults to '<owner>/<repo>' when omitted. Scanning the same repo at "
            "different refs writes to this same contract_id, so the tracked "
            "contract's latest_health_score reflects whichever ref was scanned most "
            "recently."
        ),
    )
    test_coverage_pct: float | None = Field(default=None, ge=0, le=100)
    coverage_output: str | None = Field(
        default=None,
        description=(
            "Raw output from cargo tarpaulin or cargo llvm-cov. "
            "Used to derive test coverage automatically when test_coverage_pct is omitted."
        ),
    )
    coverage_tool: CoverageTool = CoverageTool.AUTO


async def _scan_and_persist(
    *,
    contract_id: str,
    files: dict[str, str],
    test_coverage_pct: float | None,
    coverage_output: str | None,
    coverage_tool: CoverageTool,
    repo: ContractRepository,
    onchain: SorobanActivityService,
) -> ScanResult:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided to scan")

    if test_coverage_pct is None and coverage_output:
        test_coverage_pct = parse_coverage_pct(
            output=coverage_output, tool=coverage_tool
        )
        if test_coverage_pct is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Unable to parse coverage_output. Provide cargo tarpaulin/cargo llvm-cov output "
                    "or set test_coverage_pct explicitly."
                ),
            )

    findings: list[Finding] = []

    # Run per-file checks
    for path, source in files.items():
        if path.endswith(".rs"):
            findings.extend(scan_file(path, source))

    # Run cross-file checks
    findings.extend(check_dependency_version_drift(files))

    try:
        on_chain_activity = await run_in_threadpool(onchain.fetch_activity, contract_id)
    except RpcUnavailableError as exc:
        # A scan never fails outright because on-chain data couldn't be
        # fetched — static findings + coverage still score the contract.
        on_chain_activity = OnChainActivity(available=False, reason=str(exc))

    score = compute_health_score(
        findings=findings,
        test_coverage_pct=test_coverage_pct,
        severity_penalty=_SEVERITY_PENALTY,
        on_chain_activity=on_chain_activity,
    )

    result = ScanResult(
        contract_id=contract_id,
        health_score=score,
        test_coverage_pct=test_coverage_pct,
        findings=findings,
        on_chain_activity=on_chain_activity,
        scanned_at=datetime.now(timezone.utc).isoformat(),
    )
    await run_in_threadpool(repo.record_scan, result)
    return result


@router.post("/", response_model=ScanResult)
async def run_scan(
    payload: ScanSourceRequest,
    repo: ContractRepository = Depends(get_repository),
    onchain: SorobanActivityService = Depends(get_onchain_service),
) -> ScanResult:
    return await _scan_and_persist(
        contract_id=payload.contract_id,
        files=payload.files,
        test_coverage_pct=payload.test_coverage_pct,
        coverage_output=payload.coverage_output,
        coverage_tool=payload.coverage_tool,
        repo=repo,
        onchain=onchain,
    )


@router.post("/repo", response_model=ScanResult)
async def run_repo_scan(
    payload: ScanRepoRequest,
    repo: ContractRepository = Depends(get_repository),
    onchain: SorobanActivityService = Depends(get_onchain_service),
    github_client: httpx.Client = Depends(get_github_client),
) -> ScanResult:
    try:
        parsed = parse_github_repo_url(payload.repo_url)
    except InvalidRepoUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        files = await run_in_threadpool(fetch_repo_files, parsed, github_client)
    except RepoNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"GitHub repo not found: {parsed.owner}/{parsed.repo}",
        ) from exc
    except RepoFetchTimeoutError as exc:
        raise HTTPException(
            status_code=504, detail="Timed out fetching repository from GitHub"
        ) from exc
    except (RepoTooLargeError, TooManyFilesError) as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except NoScannableFilesError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"No .rs/Cargo.toml/Cargo.lock files found in {parsed.owner}/{parsed.repo}",
        ) from exc
    except GitHubFetchError as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch repository from GitHub: {exc}"
        ) from exc

    return await _scan_and_persist(
        contract_id=payload.contract_id or f"{parsed.owner}/{parsed.repo}",
        files=files,
        test_coverage_pct=payload.test_coverage_pct,
        coverage_output=payload.coverage_output,
        coverage_tool=payload.coverage_tool,
        repo=repo,
        onchain=onchain,
    )
