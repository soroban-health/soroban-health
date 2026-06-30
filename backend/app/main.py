"""Soroban Health API entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import contracts, health, scans
from app.core.config import settings

app = FastAPI(
    title="Soroban Health API",
    description="Contract observability, anti-pattern detection, and "
    "test-coverage scoring for Soroban smart contracts.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(contracts.router, prefix="/contracts", tags=["contracts"])
app.include_router(scans.router, prefix="/scans", tags=["scans"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "soroban-health-api", "status": "ok"}
