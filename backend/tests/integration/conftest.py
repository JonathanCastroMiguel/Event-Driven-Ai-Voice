from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_url() -> str:
    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url().replace("psycopg2", "asyncpg", 1)
        # Remove +asyncpg doubling if present
        url = url.replace("postgresql+asyncpg", "postgresql", 1)
        yield url  # type: ignore[misc]


@pytest.fixture(scope="session")
def _run_migrations(postgres_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(cfg, "head")


@pytest.fixture
async def pg_pool(postgres_url: str, _run_migrations: None) -> AsyncIterator[asyncpg.Pool]:
    pool: asyncpg.Pool = await asyncpg.create_pool(dsn=postgres_url, min_size=1, max_size=5)
    yield pool
    await pool.close()
