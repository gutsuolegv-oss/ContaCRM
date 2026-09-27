from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_today
from app.core.security import create_access_token
from app.db.session import get_session
from app.main import create_app
from app.models import User, UserRole
from tests.integration.factories import make_user

AuthHeaders = Callable[[UserRole], Awaitable[tuple[User, dict[str, str]]]]


@pytest.fixture
def auth(session: AsyncSession) -> AuthHeaders:
    """`user, headers = await auth(UserRole.ADMIN)`: un utilizator nou și antetul Bearer."""
    counter = 0

    async def _auth(role: UserRole) -> tuple[User, dict[str, str]]:
        nonlocal counter
        counter += 1
        user = await make_user(session, f"{role.value}{counter}", role)
        token = create_access_token(user.id, datetime.now(UTC))
        return user, {"Authorization": f"Bearer {token}"}

    return _auth


API_TODAY = date(2026, 9, 27)


@pytest.fixture
async def api(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Client HTTP cu „azi” fixat la API_TODAY (27.09.2026)."""
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield session

    async def _today() -> date:
        return API_TODAY

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_today] = _today
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
