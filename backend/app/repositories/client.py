from collections.abc import Sequence

from sqlalchemy import exists, select

from app.db.base import RecordStatus
from app.models import Client, ClientAssignment
from app.repositories.base import Repository


class ClientRepository(Repository[Client]):
    model = Client

    async def get_active(self, id_: int) -> Client | None:
        stmt = select(Client).where(
            Client.id == id_, Client.status == RecordStatus.ACTIVE, Client.deleted_at.is_(None)
        )
        return (await self.session.scalars(stmt)).one_or_none()

    async def list_active(self) -> Sequence[Client]:
        stmt = (
            select(Client)
            .where(Client.status == RecordStatus.ACTIVE, Client.deleted_at.is_(None))
            .order_by(Client.name, Client.id)
        )
        return (await self.session.scalars(stmt)).all()

    async def is_assigned_to(self, client_id: int, user_id: int) -> bool:
        """Contabilul are acum (repartizare deschisă) clientul?"""
        stmt = select(
            exists().where(
                ClientAssignment.client_id == client_id,
                ClientAssignment.user_id == user_id,
                ClientAssignment.unassigned_at.is_(None),
            )
        )
        return bool(await self.session.scalar(stmt))
