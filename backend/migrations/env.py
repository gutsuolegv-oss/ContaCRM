"""Mediul Alembic.

URL-ul vine din setările aplicației (DATABASE_URL). Testele trimit o conexiune deja deschisă
prin `config.attributes["connection"]`, ca migrările să ruleze pe baza de test.
"""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

import app.db.models  # noqa: F401  # înregistrează toate modelele în Base.metadata
from app.core.config import get_settings
from app.db.base import Base

target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


def run_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_offline()
elif (connection := context.config.attributes.get("connection")) is not None:
    _run(connection)
else:
    asyncio.run(_run_async())
