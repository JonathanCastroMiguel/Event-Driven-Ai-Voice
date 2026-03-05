"""Health check and metrics endpoints."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request, Response

logger = structlog.get_logger()

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(request: Request) -> dict[str, Any]:
    """Check asyncpg pool, Redis, and models loaded."""
    state = request.app.state
    checks: dict[str, str] = {}

    # Check asyncpg pool
    pool = getattr(state, "db_pool", None)
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            checks["database"] = "ok"
        except Exception as e:
            checks["database"] = f"error: {e}"
    else:
        checks["database"] = "not_configured"

    # Check Redis
    redis = getattr(state, "redis", None)
    if redis is not None:
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {e}"
    else:
        checks["redis"] = "not_configured"

    # Check models loaded
    models_loaded = getattr(state, "models_loaded", False)
    checks["models"] = "ok" if models_loaded else "not_loaded"

    all_ok = all(v == "ok" or v == "not_configured" for v in checks.values())
    status_code = 200 if all_ok else 503

    return {"status": "healthy" if all_ok else "degraded", "checks": checks}


@router.get("/metrics")
async def metrics(request: Request) -> Response:
    """Prometheus metrics exposition."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
