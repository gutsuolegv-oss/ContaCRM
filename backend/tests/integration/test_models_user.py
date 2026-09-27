from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import RecordStatus
from app.models import Organization, User, UserRole


@pytest.fixture
async def org(session: AsyncSession) -> Organization:
    org = Organization(name="Birou Test")
    session.add(org)
    await session.flush()
    return org


def _user(org: Organization, username: str, role: UserRole = UserRole.CONTABIL) -> User:
    return User(
        organization_id=org.id,
        username=username,
        full_name="Test",
        password_hash="x",  # noqa: S106
        role=role,
    )


async def test_user_defaults(session: AsyncSession, org: Organization) -> None:
    user = _user(org, "a")
    session.add(user)
    await session.flush()
    await session.refresh(user)
    assert user.id is not None
    assert user.status is RecordStatus.ACTIVE
    assert user.created_at is not None


async def test_username_unique_case_insensitive(session: AsyncSession, org: Organization) -> None:
    session.add(_user(org, "ana"))
    await session.flush()
    session.add(_user(org, "ANA"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_username_reusable_after_soft_delete(
    session: AsyncSession, org: Organization
) -> None:
    old = _user(org, "ion")
    session.add(old)
    await session.flush()
    old.status = RecordStatus.ARCHIVED
    old.deleted_at = datetime.now(UTC)
    await session.flush()
    session.add(_user(org, "ion"))
    await session.flush()


async def test_role_check_constraint(session: AsyncSession, org: Organization) -> None:
    with pytest.raises(IntegrityError):
        await session.execute(
            text(
                "INSERT INTO users (organization_id, username, full_name, password_hash, role) "
                "VALUES (:org, 'x', 'X', 'x', 'superuser')"
            ),
            {"org": org.id},
        )
