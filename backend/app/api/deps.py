"""Shared FastAPI dependencies for the API routes."""

from fastapi import Depends
from stellar_sdk import SorobanServer
from supabase import Client

from app.services.repository import ContractRepository
from app.services.rpc import SorobanActivityService
from app.services.soroban_client import get_soroban_server
from app.services.supabase_client import get_supabase_client


def get_repository(client: Client = Depends(get_supabase_client)) -> ContractRepository:
    return ContractRepository(client)


def get_onchain_service(
    server: SorobanServer = Depends(get_soroban_server),
) -> SorobanActivityService:
    return SorobanActivityService(server)
