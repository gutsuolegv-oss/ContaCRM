from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
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
        user = await make_user(session, f"{role.value}{counter}@birou.md", role)
        token = create_access_token(user.id, datetime.now(UTC))
        return user, {"Authorization": f"Bearer {token}"}

    return _auth
