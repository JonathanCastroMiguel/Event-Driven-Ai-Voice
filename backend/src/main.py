"""Application entry point: startup wiring and server launch."""

from __future__ import annotations

import asyncio
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

    # 5. Load embedding model and precompute centroids
    from src.routing.embeddings import EmbeddingEngine
    from src.routing.router import Router

    engine = EmbeddingEngine.load()
    router = Router(registry=registry, embedding_engine=engine)
    router.precompute_centroids()
    app.state.router = router
    app.state.models_loaded = True
    logger.info("embedding_model_loaded_and_centroids_computed")

    # 5b. Load model-as-router prompt template
    from src.routing.model_router import RouterPromptBuilder, load_router_prompt

    router_prompt_template = load_router_prompt(settings.router_registry_path)
    router_prompt_builder = RouterPromptBuilder(router_prompt_template)
    app.state.router_prompt_builder = router_prompt_builder
    logger.info("router_prompt_builder_loaded")

    # 5c. Wire shared dependencies for call sessions
    from src.api.routes.calls import set_shared_dependencies

    set_shared_dependencies(router_prompt_builder, policies)
    logger.info("shared_dependencies_wired")

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
    await db_pool.close()
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
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        loop="uvloop",
        log_level="info",
    )
