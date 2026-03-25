"""Application entry point: startup wiring and server launch."""

from __future__ import annotations

import asyncio
import signal
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
import uvicorn

from src.config import settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle: create pools, load models, wire actors."""
    # --- Startup ---
    logger.info("startup_begin")

    # 0. Initialize telemetry and Sentry
    from src.infrastructure.telemetry import setup_sentry, setup_telemetry

    setup_telemetry(settings)
    setup_sentry(settings)

    # 1. Create asyncpg pool
    from src.infrastructure.db import create_asyncpg_pool

    db_pool = await create_asyncpg_pool(settings)
    app.state.db_pool = db_pool
    logger.info("asyncpg_pool_created")

    # 2. Create Redis pool
    from src.infrastructure.redis_client import create_redis_pool

    redis = await create_redis_pool(settings)
    app.state.redis = redis
    logger.info("redis_pool_created")

    # 3. Load router registry
    from src.routing.registry import load_registry

    registry = load_registry(settings.router_registry_path)
    app.state.registry = registry
    logger.info("router_registry_loaded", version=registry.thresholds.version)

    # 4. Load policies
    from src.routing.policies import load_policies

    policies = load_policies(settings.router_registry_path)
    app.state.policies = policies
    logger.info("policies_loaded")

    # 5. Load model-as-router prompt template
    from src.routing.model_router import RouterPromptBuilder, load_router_prompt

    router_prompt_config = load_router_prompt(settings.router_registry_path)
    router_prompt_builder = RouterPromptBuilder(router_prompt_config)
    app.state.router_prompt_builder = router_prompt_builder
    logger.info("router_prompt_builder_loaded")

    # 5c. Wire shared dependencies for call sessions
    from src.api.routes.calls import set_shared_dependencies

    set_shared_dependencies(router_prompt_builder, policies)
    logger.info("shared_dependencies_wired")

    # 5d. Create SessionRepository with RedisSessionRegistry
    from src.infrastructure.session_registry import RedisSessionRegistry
    from src.infrastructure.session_repository import SessionRepository

    redis_session_registry = RedisSessionRegistry(redis)
    session_repository = SessionRepository(
        max_sessions_per_process=settings.max_concurrent_calls,
        redis_registry=redis_session_registry,
        shutdown_timeout=settings.graceful_shutdown_timeout,
    )
    app.state.session_repository = session_repository
    logger.info("session_repository_initialized", max_sessions=settings.max_concurrent_calls)

    # 6. Store repositories for coordinator usage
    from src.infrastructure.repositories import (
        PgAgentGenerationRepository,
        PgCallRepository,
        PgTurnRepository,
        PgVoiceGenerationRepository,
    )

    app.state.call_repo = PgCallRepository(db_pool)
    app.state.turn_repo = PgTurnRepository(db_pool)
    app.state.agent_gen_repo = PgAgentGenerationRepository(db_pool)
    app.state.voice_gen_repo = PgVoiceGenerationRepository(db_pool)

    logger.info("startup_complete")

    yield

    # --- Shutdown ---
    logger.info("shutdown_begin")
    logger.info("graceful_shutdown_timeout_config", timeout_seconds=settings.graceful_shutdown_timeout)
    
    # Gracefully shut down sessions
    try:
        session_repository = app.state.session_repository
        logger.info("calling_session_repository_shutdown")
        await session_repository.shutdown()
        logger.info("session_repository_shutdown_returned")
    except Exception as e:
        logger.error("session_repository_shutdown_error", error=str(e), exc_info=True)
    
    logger.info("closing_db_pool")
    await db_pool.close()
    logger.info("closing_redis")
    await redis.aclose()
    logger.info("shutdown_complete")


def create_configured_app() -> FastAPI:
    """Create the fully configured FastAPI app with lifespan."""
    from src.api.app import create_app

    app = create_app()
    app.router.lifespan_context = lifespan
    return app


app = create_configured_app()

if __name__ == "__main__":
    # Configure Uvicorn with proper shutdown handling
    config = uvicorn.Config(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        loop="uvloop",
        log_level="info",
        timeout_shutdown=30,  # Wait up to 30 seconds for graceful shutdown
        timeout_keep_alive=5,
    )
    server = uvicorn.Server(config)
    
    # Setup signal handler for graceful shutdown
    def signal_handler(sig, frame):  # type: ignore[no-untyped-def]
        logger.info("signal_received_initiating_shutdown", signal_number=sig)
        server.should_exit = True
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("starting_server", host=settings.host, port=settings.port)
    asyncio.run(server.serve())
