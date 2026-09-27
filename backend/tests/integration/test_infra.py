from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_session_uses_test_database(session: AsyncSession) -> None:
    name = await session.scalar(text("SELECT current_database()"))
    assert name is not None and name.endswith("_test")


async def test_session_is_rolled_back(session: AsyncSession) -> None:
    await session.execute(text("CREATE TABLE _rollback_probe (id int)"))
    await session.commit()  # commit pe savepoint; tranzacția exterioară se anulează la final
    count = await session.scalar(
        text("SELECT count(*) FROM pg_tables WHERE tablename = '_rollback_probe'")
    )
    assert count == 1


# Rulează după testul de mai sus (pytest păstrează ordinea din fișier).
async def test_previous_test_left_nothing(session: AsyncSession) -> None:
    count = await session.scalar(
        text("SELECT count(*) FROM pg_tables WHERE tablename = '_rollback_probe'")
    )
    assert count == 0
