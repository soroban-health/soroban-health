"""Pydantic models for contract metadata."""

from pydantic import BaseModel, Field


class ContractRegisterRequest(BaseModel):
    contract_id: str = Field(..., description="Soroban contract address, e.g. CABC...")
    network: str = Field(default="testnet", description="testnet | mainnet")
    label: str | None = Field(default=None, description="Human-friendly name for the dashboard")


class ContractSummary(BaseModel):
    contract_id: str
    network: str
    label: str | None
    latest_health_score: float | None = None
    last_scanned_at: str | None = None
