"""Lazily-constructed Soroban RPC client, shared across requests."""

from functools import lru_cache

from stellar_sdk import SorobanServer

from app.core.config import settings


@lru_cache
def get_soroban_server() -> SorobanServer:
    return SorobanServer(settings.SOROBAN_RPC_URL)
