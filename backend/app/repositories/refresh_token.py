from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, user_id: int, token_hash: str, expires_at: datetime) -> None:
        self.session.add(
            RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        )

    async def get_by_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        """Blochează rândul, ca două cereri simultane să nu folosească același token."""
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        )
        return result.scalar_one_or_none()

    async def revoke_all_for_user(self, user_id: int, now: datetime) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
