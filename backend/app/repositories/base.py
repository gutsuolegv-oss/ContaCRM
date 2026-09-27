from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

M = TypeVar("M", bound=Base)


class Repository(Generic[M]):
    """Acces la un singur model. Subclasele adaugă interogările specifice."""

    model: type[M]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id_: int) -> M | None:
        return await self.session.get(self.model, id_)

    def add(self, obj: M) -> None:
        self.session.add(obj)

    async def delete(self, obj: M) -> None:
        await self.session.delete(obj)
