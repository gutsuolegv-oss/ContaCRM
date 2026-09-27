"""Clienții: cartela, conturile bancare, contactele și contabilii repartizați.

Permisiuni:
- admin și director: toți clienții, orice modificare, arhivare, repartizări, `client_status`;
- contabilul: doar clienții repartizați lui — citire și modificarea cartelei (inclusiv
  atributele pentru reguli), conturi, contacte; poate adăuga clienți, care i se repartizează
  automat și rămân în `onboarding` până îi activează un admin sau directorul.

Când se schimbă un atribut pe care se evaluează regulile (sau la crearea clientului),
obligațiile se recalculează automat, cu data de azi.
"""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import RecordStatus
from app.models import (
    Client,
    ClientAssignment,
    ClientBankAccount,
    ClientContact,
    User,
)
from app.repositories.client import (
    AssignmentRepository,
    BankAccountRepository,
    ClientRepository,
    ContactRepository,
)
from app.repositories.user import UserRepository
from app.schemas.clients import (
    BankAccountCreate,
    BankAccountOut,
    BankAccountUpdate,
    ClientCreate,
    ClientListItem,
    ClientOut,
    ClientUpdate,
    ContactCreate,
    ContactOut,
    ContactUpdate,
    UserBrief,
)
from app.schemas.conditions import CLIENT_RULE_FIELDS
from app.schemas.matrix import RecalculateDiff
from app.services.access import SEES_ALL_CLIENTS
from app.services.audit import AuditService, snapshot
from app.services.classifier import apply_changes
from app.services.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
    conflict_guard,
)
from app.services.matrix import MatrixService

_IDNO_CONFLICT = "Există deja un client activ cu acest IDNO"


def _accountants(client: Client) -> list[UserBrief]:
    """Contabilii actuali. Repository-ul încarcă doar repartizările deschise."""
    return [UserBrief.model_validate(a.user) for a in client.assignments if a.unassigned_at is None]


def client_out(client: Client) -> ClientOut:
    """Cartela pentru API (clientul încărcat cu ClientRepository.get_card)."""
    skip = {"accountants", "bank_accounts", "contacts"}
    data = {k: getattr(client, k) for k in ClientOut.model_fields if k not in skip}
    data |= {
        "accountants": _accountants(client),
        "bank_accounts": [BankAccountOut.model_validate(a) for a in client.bank_accounts],
        "contacts": [ContactOut.model_validate(c) for c in client.contacts],
    }
    return ClientOut.model_validate(data)


def client_list_item(client: Client) -> ClientListItem:
    data = {k: getattr(client, k) for k in ClientListItem.model_fields if k != "accountants"}
    return ClientListItem.model_validate(data | {"accountants": _accountants(client)})


class ClientService:
    def __init__(self, session: AsyncSession, actor: User) -> None:
        self.session = session
        self.actor = actor
        self.audit = AuditService(session, actor)
        self.clients = ClientRepository(session)
        self.accounts = BankAccountRepository(session)
        self.contacts = ContactRepository(session)
        self.assignments = AssignmentRepository(session)

    @property
    def is_editor(self) -> bool:
        return self.actor.role in SEES_ALL_CLIENTS

    def _require_editor(self) -> None:
        if not self.is_editor:
            raise ForbiddenError("Doar admin și director")

    # --- Citire ---

    async def search(self, **filters: Any) -> tuple[int, Sequence[Client]]:
        if not self.is_editor:
            filters["only_ids"] = await self.clients.assigned_ids(self.actor.id)
            filters["include_archived"] = False
        return await self.clients.search(**filters)

    async def get_card(self, client_id: int) -> Client:
        """Cartela, dacă utilizatorul o poate vedea. Arhivații: doar admin și director."""
        client = await self.clients.get_card(client_id, include_archived=self.is_editor)
        if client is None or not await self._sees(client.id):
            raise NotFoundError("Clientul nu există")
        return client

    async def _sees(self, client_id: int) -> bool:
        return self.is_editor or await self.clients.is_assigned_to(client_id, self.actor.id)

    async def _editable(self, client_id: int) -> Client:
        """Client activ (nearhivat), vizibil utilizatorului: pe el se poate lucra."""
        client = await self.clients.get_active(client_id)
        if client is None or not await self._sees(client.id):
            raise NotFoundError("Clientul nu există")
        return client

    # --- Client ---

    async def create(self, data: ClientCreate, today: date) -> tuple[Client, RecalculateDiff]:
        client = Client(**data.model_dump(), created_by=self.actor.id)
        async with conflict_guard(self.session, _IDNO_CONFLICT):
            self.session.add(client)
        self.audit.created(client)
        if not self.is_editor:  # contabilul: clientul i se repartizează lui
            await self._add_assignment(client.id, self.actor.id)
        await self.session.commit()
        diff = await self._recalculate(client, today)
        return await self.get_card(client.id), diff

    async def update(
        self, client_id: int, data: ClientUpdate, today: date
    ) -> tuple[Client, RecalculateDiff | None]:
        client = await self._editable(client_id)
        values = data.model_dump(exclude_unset=True)
        if "client_status" in values and not self.is_editor:
            raise ForbiddenError("Doar admin și director schimbă statusul clientului")

        # vat_code are sens doar la plătitorii de TVA
        is_payer = values.get("is_vat_payer", client.is_vat_payer)
        if not is_payer:
            if values.get("vat_code") is not None:
                raise ValidationFailedError("vat_code se completează doar la plătitorii de TVA")
            if client.vat_code is not None:
                values["vat_code"] = None

        before = snapshot(client)
        async with conflict_guard(self.session, _IDNO_CONFLICT):
            apply_changes(client, values)
        self.audit.changed(client, before)
        await self.session.commit()

        rules_changed = any(before[f] != snapshot(client)[f] for f in CLIENT_RULE_FIELDS)
        diff = await self._recalculate(client, today) if rules_changed else None
        return await self.get_card(client.id), diff

    async def archive(self, client_id: int, now: datetime) -> None:
        self._require_editor()
        client = await self._editable(client_id)
        before = snapshot(client)
        async with conflict_guard(self.session, "Clientul nu a putut fi arhivat"):
            client.status = RecordStatus.ARCHIVED
            client.deleted_at = now
            client.deleted_by = self.actor.id
        self.audit.changed(client, before)
        await self.session.commit()

    async def _recalculate(self, client: Client, today: date) -> RecalculateDiff:
        plan = await MatrixService(self.session, self.actor).apply(client, today)
        return plan.to_diff()

    # --- Conturi bancare ---

    async def add_bank_account(self, client_id: int, data: BankAccountCreate) -> Client:
        client = await self._editable(client_id)
        async with conflict_guard(self.session, "Clientul are deja acest IBAN"):
            if data.is_primary:
                await self._unset_primary(await self.accounts.primary_of(client.id))
            account = ClientBankAccount(client_id=client.id, **data.model_dump())
            self.session.add(account)
        self.audit.created(account)
        await self.session.commit()
        return await self.get_card(client.id)

    async def _account(self, account_id: int) -> ClientBankAccount:
        account = await self.accounts.get_active(account_id)
        if account is None or not await self._sees(account.client_id):
            raise NotFoundError("Contul nu există")
        await self._editable(account.client_id)
        return account

    async def update_bank_account(self, account_id: int, data: BankAccountUpdate) -> Client:
        account = await self._account(account_id)
        values = data.model_dump(exclude_unset=True)
        before = snapshot(account)
        async with conflict_guard(self.session, "Clientul are deja acest IBAN"):
            if values.get("is_primary") and not account.is_primary:
                await self._unset_primary(await self.accounts.primary_of(account.client_id))
            apply_changes(account, values)
        self.audit.changed(account, before)
        await self.session.commit()
        return await self.get_card(account.client_id)

    async def delete_bank_account(self, account_id: int, now: datetime) -> Client:
        account = await self._account(account_id)
        await self._soft_delete(account, now)
        return await self.get_card(account.client_id)

    # --- Contacte ---

    async def add_contact(self, client_id: int, data: ContactCreate) -> Client:
        client = await self._editable(client_id)
        async with conflict_guard(self.session, "Contactul nu a putut fi salvat"):
            if data.is_primary:
                await self._unset_primary(await self.contacts.primary_of(client.id))
            contact = ClientContact(client_id=client.id, **data.model_dump())
            self.session.add(contact)
        self.audit.created(contact)
        await self.session.commit()
        return await self.get_card(client.id)

    async def _contact(self, contact_id: int) -> ClientContact:
        contact = await self.contacts.get_active(contact_id)
        if contact is None or not await self._sees(contact.client_id):
            raise NotFoundError("Contactul nu există")
        await self._editable(contact.client_id)
        return contact

    async def update_contact(self, contact_id: int, data: ContactUpdate) -> Client:
        contact = await self._contact(contact_id)
        values = data.model_dump(exclude_unset=True)
        before = snapshot(contact)
        async with conflict_guard(self.session, "Contactul nu a putut fi salvat"):
            if values.get("is_primary") and not contact.is_primary:
                await self._unset_primary(await self.contacts.primary_of(contact.client_id))
            apply_changes(contact, values)
        self.audit.changed(contact, before)
        await self.session.commit()
        return await self.get_card(contact.client_id)

    async def delete_contact(self, contact_id: int, now: datetime) -> Client:
        contact = await self._contact(contact_id)
        await self._soft_delete(contact, now)
        return await self.get_card(contact.client_id)

    # --- comune conturi / contacte ---

    async def _unset_primary(self, rows: Sequence[ClientBankAccount | ClientContact]) -> None:
        """Principalul vechi pierde marcajul; se scrie înainte de cel nou (index unic)."""
        for row in rows:
            before = snapshot(row)
            row.is_primary = False
            await self.session.flush()
            self.audit.changed(row, before)

    async def _soft_delete(self, row: ClientBankAccount | ClientContact, now: datetime) -> None:
        before = snapshot(row)
        async with conflict_guard(self.session, "Înregistrarea nu a putut fi ștearsă"):
            row.status = RecordStatus.ARCHIVED
            row.deleted_at = now
            row.deleted_by = self.actor.id
            row.is_primary = False
        self.audit.changed(row, before)
        await self.session.commit()

    # --- Repartizări ---

    async def assignment_history(self, client_id: int) -> Sequence[ClientAssignment]:
        await self.get_card(client_id)
        return await self.assignments.history(client_id)

    async def assign(self, client_id: int, user_id: int) -> Sequence[ClientAssignment]:
        self._require_editor()
        client = await self._editable(client_id)
        if await UserRepository(self.session).get_active(user_id) is None:
            raise ValidationFailedError("Utilizatorul nu există")
        if await self.assignments.current(client.id, user_id) is not None:
            raise ConflictError("Utilizatorul e deja repartizat acestui client")
        await self._add_assignment(client.id, user_id)
        await self.session.commit()
        return await self.assignments.history(client.id)

    async def _add_assignment(self, client_id: int, user_id: int) -> None:
        assignment = ClientAssignment(
            client_id=client_id, user_id=user_id, assigned_by=self.actor.id
        )
        async with conflict_guard(self.session, "Utilizatorul e deja repartizat"):
            self.session.add(assignment)
        self.audit.created(assignment)

    async def unassign(self, assignment_id: int, now: datetime) -> Sequence[ClientAssignment]:
        self._require_editor()
        assignment = await self.assignments.get(assignment_id)
        if assignment is None:
            raise NotFoundError("Repartizarea nu există")
        if assignment.unassigned_at is None:
            before = snapshot(assignment)
            async with conflict_guard(self.session, "Repartizarea nu a putut fi închisă"):
                assignment.unassigned_at = now
                assignment.unassigned_by = self.actor.id
            self.audit.changed(assignment, before)
            await self.session.commit()
        return await self.assignments.history(assignment.client_id)
