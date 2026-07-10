"""Pydantic models for contract metadata."""

import re

from pydantic import BaseModel, Field, field_validator

_STELLAR_CONTRACT_ID_RE = re.compile(r"^C[A-Z2-7]{55}$")


class ContractRegisterRequest(BaseModel):
    contract_id: str = Field(..., description="Soroban contract address, e.g. CABC...")
    network: str = Field(default="testnet", description="testnet | mainnet")
    label: str | None = Field(default=None, description="Human-friendly name for the dashboard")

    @field_validator("contract_id")
    @classmethod
    def validate_contract_id(cls, value: str) -> str:
        if not _STELLAR_CONTRACT_ID_RE.fullmatch(value):
            raise ValueError(
                "contract_id must be a Stellar contract address (56 chars, starts with 'C', and uses A-Z2-7)"
            )
        return value


class ContractSummary(BaseModel):
    contract_id: str
    network: str
    label: str | None
    latest_health_score: float | None = None
    last_scanned_at: str | None = None
