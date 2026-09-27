from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Base
from tests.conftest import alembic_config


def _diff(connection: Connection) -> list[object]:
    ctx = MigrationContext.configure(
        connection, opts={"compare_type": True, "compare_server_default": True}
    )
    diff: list[object] = compare_metadata(ctx, Base.metadata)
    return diff


async def test_models_match_migrations(session: AsyncSession) -> None:
    """Dacă pică: s-a modificat un model fără migrare (`alembic revision --autogenerate`)."""
    conn = await session.connection()
    assert await conn.run_sync(_diff) == []


async def test_downgrade_and_upgrade_again(session: AsyncSession) -> None:
    """Fiecare migrare se poate anula și reaplica (în tranzacția testului, deci fără efect)."""
    conn = await session.connection()
    await conn.run_sync(lambda c: command.downgrade(alembic_config(c), "base"))
    await conn.run_sync(lambda c: command.upgrade(alembic_config(c), "head"))
    assert await conn.run_sync(_diff) == []
