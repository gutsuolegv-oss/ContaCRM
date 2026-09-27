"""Cine ce clienți vede: admin și director — toți; contabilul — doar clienții repartizați lui."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, User, UserRole
from app.repositories.client import ClientRepository
from app.services.errors import NotFoundError

SEES_ALL_CLIENTS = {UserRole.ADMIN, UserRole.DIRECTOR}


async def get_visible_client(session: AsyncSession, user: User, client_id: int) -> Client:
    """Clientul, dacă există și utilizatorul îl poate vedea. Altfel NotFoundError (același
    răspuns în ambele cazuri, ca să nu se afle ce clienți există)."""
    clients = ClientRepository(session)
    client = await clients.get_active(client_id)
    if client is None:
        raise NotFoundError("Clientul nu există")
    if user.role not in SEES_ALL_CLIENTS and not await clients.is_assigned_to(client.id, user.id):
        raise NotFoundError("Clientul nu există")
    return client
