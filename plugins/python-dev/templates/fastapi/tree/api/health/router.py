"""Health endpoint — HTTP concerns only; logic lives in service.py."""

from fastapi import APIRouter

from api.health.model import HealthResponse
from api.health.service import check_health

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return check_health()
