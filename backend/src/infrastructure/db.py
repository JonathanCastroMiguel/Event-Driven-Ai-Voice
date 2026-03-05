from __future__ import annotations

import asyncpg
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.config import Settings


async def create_asyncpg_pool(settings: Settings) -> asyncpg.Pool:
    pool: asyncpg.Pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
    )
    return pool


def create_sa_engine(settings: Settings) -> AsyncEngine:
    sa_url = settings.database_url.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
    return create_async_engine(sa_url, pool_size=5, max_overflow=5)
