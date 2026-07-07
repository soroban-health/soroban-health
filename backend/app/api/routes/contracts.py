"""Routes for registering and listing tracked contracts."""

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_repository
from app.models.contract import ContractRegisterRequest, ContractSummary
from app.services.repository import ContractRepository

router = APIRouter()


@router.post("/", response_model=ContractSummary, status_code=201)
async def register_contract(
    payload: ContractRegisterRequest,
    repo: ContractRepository = Depends(get_repository),
) -> ContractSummary:
    # NOTE: get-then-insert reintroduces a TOCTOU race the old in-memory
    # dict never had (two concurrent requests could both pass this check).
    # Acceptable v0 tradeoff; hardening it would mean catching a Postgres
    # unique-violation from the insert instead.
    existing = await run_in_threadpool(repo.get_contract, payload.contract_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Contract already registered")
    return await run_in_threadpool(repo.register_contract, payload)


@router.get("/", response_model=list[ContractSummary])
async def list_contracts(
    repo: ContractRepository = Depends(get_repository),
) -> list[ContractSummary]:
    return await run_in_threadpool(repo.list_contracts)


@router.get("/{contract_id}", response_model=ContractSummary)
async def get_contract(
    contract_id: str,
    repo: ContractRepository = Depends(get_repository),
) -> ContractSummary:
    summary = await run_in_threadpool(repo.get_contract, contract_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return summary
