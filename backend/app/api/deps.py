"""Shared FastAPI dependencies for the API routes."""

from fastapi import Depends
from supabase import Client

from app.services.repository import ContractRepository
from app.services.supabase_client import get_supabase_client


def get_repository(client: Client = Depends(get_supabase_client)) -> ContractRepository:
    return ContractRepository(client)
