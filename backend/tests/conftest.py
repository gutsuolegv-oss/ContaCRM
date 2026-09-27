"""Fixtures comune.

Testele rulează pe o bază separată, <POSTGRES_DB>_test, creată automat pe același server
PostgreSQL. Fiecare test primește o sesiune într-o tranzacție care se anulează la final,
deci testele nu își lasă date unul altuia.
"""

import os

os.environ.setdefault("ENVIRONMENT", "test")

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app


def _test_database_url() -> URL:
    url = make_url(get_settings().database_url)
    name = f"{url.database}_test"
    assert name.endswith("_test"), "Testele trebuie să ruleze doar pe o bază *_test"
    return url.set(database=name)


async def _ensure_database(url: URL) -> None:
    admin = create_async_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    async with admin.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    await admin.dispose()


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    url = _test_database_url()
    await _ensure_database(url)
    engine = create_async_engine(url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
