"""FastAPI application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Voice AI Runtime",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID middleware
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: object) -> Response:  # noqa: ANN001
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response: Response = await call_next(request)  # type: ignore[misc]
        response.headers["X-Request-ID"] = request_id
        structlog.contextvars.unbind_contextvars("request_id")
        return response

    # Error middleware
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # Import and include routers
    from src.api.routes.health import router as health_router
    from src.api.routes.admin import router as admin_router

    app.include_router(health_router)
    app.include_router(admin_router, prefix="/api/v1")

    return app
