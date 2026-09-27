from collections.abc import Sequence

from sqlalchemy import ColumnElement, Select, and_, exists, func, or_, select
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.db.base import RecordStatus
from app.models import (
    Client,
    ClientAssignment,
    ClientBankAccount,
    ClientContact,
    ClientStatus,
)
from app.repositories.base import Repository


def _not_deleted(
    model: type[Client] | type[ClientBankAccount] | type[ClientContact],
) -> ColumnElement[bool]:
    return and_(model.status == RecordStatus.ACTIVE, model.deleted_at.is_(None))


# Cartela: conturile și contactele neșterse, contabilii actuali (cu datele lor).
_CARD_OPTIONS = (
    selectinload(Client.bank_accounts),
    selectinload(Client.contacts),
    selectinload(Client.assignments).selectinload(ClientAssignment.user),
    with_loader_criteria(ClientBankAccount, _not_deleted(ClientBankAccount)),
    with_loader_criteria(ClientContact, _not_deleted(ClientContact)),
    with_loader_criteria(ClientAssignment, ClientAssignment.unassigned_at.is_(None)),
)


class ClientRepository(Repository[Client]):
    model = Client

    async def get_active(self, id_: int) -> Client | None:
        stmt = select(Client).where(Client.id == id_, _not_deleted(Client))
        return (await self.session.scalars(stmt)).one_or_none()

    async def get_card(self, id_: int, include_archived: bool = False) -> Client | None:
        """Clientul cu conturile, contactele și contabilii actuali."""
        stmt = (
            select(Client)
            .where(Client.id == id_)
            .options(*_CARD_OPTIONS)
            .execution_options(populate_existing=True)
        )
        if not include_archived:
            stmt = stmt.where(_not_deleted(Client))
        return (await self.session.scalars(stmt)).one_or_none()

    async def list_active(self) -> Sequence[Client]:
        stmt = select(Client).where(_not_deleted(Client)).order_by(Client.name, Client.id)
        return (await self.session.scalars(stmt)).all()

    async def search(
        self,
        *,
        q: str | None = None,
        client_status: ClientStatus | None = None,
        is_vat_payer: bool | None = None,
        assigned_user_id: int | None = None,
        only_ids: set[int] | None = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, Sequence[Client]]:
        """(total, pagina). `q` caută în denumire (oriunde) și în IDNO (de la început)."""
        stmt: Select[tuple[Client]] = select(Client)
        if not include_archived:
            stmt = stmt.where(_not_deleted(Client))
        if q:
            term = q.strip()
            stmt = stmt.where(
                or_(
                    func.lower(Client.name).contains(term.lower(), autoescape=True),
                    Client.idno.startswith(term, autoescape=True),
                )
            )
        if client_status is not None:
            stmt = stmt.where(Client.client_status == client_status)
        if is_vat_payer is not None:
            stmt = stmt.where(Client.is_vat_payer.is_(is_vat_payer))
        if assigned_user_id is not None:
            stmt = stmt.where(
                exists().where(
                    ClientAssignment.client_id == Client.id,
                    ClientAssignment.user_id == assigned_user_id,
                    ClientAssignment.unassigned_at.is_(None),
                )
            )
        if only_ids is not None:
            stmt = stmt.where(Client.id.in_(only_ids))

        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        page = (
            stmt.options(
                selectinload(Client.assignments).selectinload(ClientAssignment.user),
                with_loader_criteria(ClientAssignment, ClientAssignment.unassigned_at.is_(None)),
            )
            .order_by(Client.name, Client.id)
            .limit(limit)
            .offset(offset)
        )
        return total or 0, (await self.session.scalars(page)).all()

    async def assigned_ids(self, user_id: int) -> set[int]:
        """Clienții repartizați acum contabilului."""
        rows = await self.session.scalars(
            select(ClientAssignment.client_id).where(
                ClientAssignment.user_id == user_id, ClientAssignment.unassigned_at.is_(None)
            )
        )
        return set(rows.all())

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


class BankAccountRepository(Repository[ClientBankAccount]):
    model = ClientBankAccount

    async def get_active(self, id_: int) -> ClientBankAccount | None:
        stmt = select(ClientBankAccount).where(
            ClientBankAccount.id == id_, _not_deleted(ClientBankAccount)
        )
        return (await self.session.scalars(stmt)).one_or_none()

    async def primary_of(self, client_id: int) -> Sequence[ClientBankAccount]:
        stmt = select(ClientBankAccount).where(
            ClientBankAccount.client_id == client_id,
            ClientBankAccount.is_primary.is_(True),
            _not_deleted(ClientBankAccount),
        )
        return (await self.session.scalars(stmt)).all()


class ContactRepository(Repository[ClientContact]):
    model = ClientContact

    async def get_active(self, id_: int) -> ClientContact | None:
        stmt = select(ClientContact).where(ClientContact.id == id_, _not_deleted(ClientContact))
        return (await self.session.scalars(stmt)).one_or_none()

    async def primary_of(self, client_id: int) -> Sequence[ClientContact]:
        stmt = select(ClientContact).where(
            ClientContact.client_id == client_id,
            ClientContact.is_primary.is_(True),
            _not_deleted(ClientContact),
        )
        return (await self.session.scalars(stmt)).all()


class AssignmentRepository(Repository[ClientAssignment]):
    model = ClientAssignment

    async def history(self, client_id: int) -> Sequence[ClientAssignment]:
        stmt = (
            select(ClientAssignment)
            .where(ClientAssignment.client_id == client_id)
            .options(selectinload(ClientAssignment.user))
            .order_by(ClientAssignment.assigned_at.desc(), ClientAssignment.id.desc())
        )
        return (await self.session.scalars(stmt)).all()

    async def current_for_clients(self, client_ids: Sequence[int]) -> Sequence[ClientAssignment]:
        """Repartizările deschise ale mai multor clienți, cu utilizatorul (o singură interogare)."""
        stmt = (
            select(ClientAssignment)
            .where(
                ClientAssignment.client_id.in_(client_ids),
                ClientAssignment.unassigned_at.is_(None),
            )
            .options(selectinload(ClientAssignment.user))
            .order_by(ClientAssignment.assigned_at, ClientAssignment.id)
        )
        return (await self.session.scalars(stmt)).all()

    async def current(self, client_id: int, user_id: int) -> ClientAssignment | None:
        stmt = select(ClientAssignment).where(
            ClientAssignment.client_id == client_id,
            ClientAssignment.user_id == user_id,
            ClientAssignment.unassigned_at.is_(None),
        )
        return (await self.session.scalars(stmt)).one_or_none()
