"""GET /api/health — database and Bedrock status."""
from fastapi import APIRouter

from backend.api.schemas import HealthResponse
from backend.services.bedrock_service import embed_text
from backend.services.database import health_check as db_health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    db_ok = "ok" if await db_health() else "error"
    bedrock_ok = "ok"
    try:
        embed_text("test")
    except Exception:
        bedrock_ok = "error"
    return HealthResponse(database=db_ok, bedrock=bedrock_ok)
