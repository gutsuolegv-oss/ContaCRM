from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import RecordStatus
from app.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active(self, user_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(
                User.id == user_id,
                User.status == RecordStatus.ACTIVE,
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_active_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(User).where(
                func.lower(User.username) == username.strip().lower(),
                User.status == RecordStatus.ACTIVE,
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    def add(self, user: User) -> None:
        self.session.add(user)
