"""Routes for registering and listing tracked contracts."""

from fastapi import APIRouter, HTTPException

from app.models.contract import ContractRegisterRequest, ContractSummary

router = APIRouter()

# NOTE: in-memory placeholder. Issue #TBD tracks wiring this to Supabase
# (see `docs/architecture.md`). Kept intentionally simple so the API
# contract is reviewable before persistence is added.
_REGISTRY: dict[str, ContractSummary] = {}


@router.post("/", response_model=ContractSummary, status_code=201)
async def register_contract(payload: ContractRegisterRequest) -> ContractSummary:
    if payload.contract_id in _REGISTRY:
        raise HTTPException(status_code=409, detail="Contract already registered")
    summary = ContractSummary(
        contract_id=payload.contract_id,
        network=payload.network,
        label=payload.label,
    )
    _REGISTRY[payload.contract_id] = summary
    return summary


@router.get("/", response_model=list[ContractSummary])
async def list_contracts() -> list[ContractSummary]:
    return list(_REGISTRY.values())


@router.get("/{contract_id}", response_model=ContractSummary)
async def get_contract(contract_id: str) -> ContractSummary:
    summary = _REGISTRY.get(contract_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return summary
