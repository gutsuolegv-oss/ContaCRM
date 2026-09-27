from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import RecordStatus
from app.models import (
    Client,
    ClientAssignment,
    ClientBankAccount,
    ClientContact,
    ClientStatus,
    LegalForm,
    Organization,
    User,
    UserRole,
)

IBAN = "MD24AG000000022512345678"


@pytest.fixture
async def client_row(session: AsyncSession) -> Client:
    c = Client(name="Agro-Nord SRL", idno="1003600012345", legal_form=LegalForm.SRL)
    session.add(c)
    await session.flush()
    return c


async def _users(session: AsyncSession, n: int) -> list[User]:
    org = Organization(name="Birou")
    session.add(org)
    await session.flush()
    users = [
        User(
            organization_id=org.id,
            email=f"c{i}@birou.md",
            full_name=f"Contabil {i}",
            password_hash="x",  # noqa: S106
            role=UserRole.CONTABIL,
        )
        for i in range(n)
    ]
    session.add_all(users)
    await session.flush()
    return users


async def _expect_rejected(session: AsyncSession, obj: object) -> None:
    """Baza refuză rândul: constrângere încălcată sau valoare prea lungă."""
    session.add(obj)
    with pytest.raises(DBAPIError):  # IntegrityError e o subclasă
        await session.flush()


async def test_client_defaults(session: AsyncSession, client_row: Client) -> None:
    await session.refresh(client_row)
    assert client_row.client_status is ClientStatus.ONBOARDING
    assert client_row.status is RecordStatus.ACTIVE
    assert client_row.is_vat_payer is False


@pytest.mark.parametrize("idno", ["123", "10036000123456", "100360001234A"])
async def test_idno_must_be_13_digits(session: AsyncSession, idno: str) -> None:
    await _expect_rejected(session, Client(name="X", idno=idno, legal_form=LegalForm.SRL))


async def test_idno_unique_among_non_deleted(session: AsyncSession, client_row: Client) -> None:
    client_row.status = RecordStatus.ARCHIVED
    client_row.deleted_at = datetime.now(UTC)
    await session.flush()
    session.add(Client(name="Agro-Nord nou", idno=client_row.idno, legal_form=LegalForm.SRL))
    await session.flush()
    await _expect_rejected(
        session, Client(name="Dublură", idno=client_row.idno, legal_form=LegalForm.SRL)
    )


async def test_vat_code_only_for_vat_payers(session: AsyncSession) -> None:
    session.add(
        Client(
            name="A",
            idno="1000000000001",
            legal_form=LegalForm.SA,
            is_vat_payer=True,
            vat_code="0600012",
        )
    )
    await session.flush()
    await _expect_rejected(
        session,
        Client(name="B", idno="1000000000002", legal_form=LegalForm.SRL, vat_code="0600013"),
    )


@pytest.mark.parametrize("iban", ["MD24 AG00 0000 0225 1234 5678", "RO49AAAA1B31007593840000"])
async def test_iban_format(session: AsyncSession, client_row: Client, iban: str) -> None:
    await _expect_rejected(
        session, ClientBankAccount(client_id=client_row.id, bank_name="MAIB", iban=iban)
    )


async def test_one_primary_bank_account(session: AsyncSession, client_row: Client) -> None:
    session.add(
        ClientBankAccount(client_id=client_row.id, bank_name="MAIB", iban=IBAN, is_primary=True)
    )
    await session.flush()
    await _expect_rejected(
        session,
        ClientBankAccount(
            client_id=client_row.id,
            bank_name="Victoriabank",
            iban="MD68VI000000022512345678",
            is_primary=True,
        ),
    )


async def test_one_primary_contact(session: AsyncSession, client_row: Client) -> None:
    session.add(ClientContact(client_id=client_row.id, full_name="Petru", is_primary=True))
    await session.flush()
    session.add(ClientContact(client_id=client_row.id, full_name="Natalia"))  # nu e principal
    await session.flush()
    await _expect_rejected(
        session, ClientContact(client_id=client_row.id, full_name="Ion", is_primary=True)
    )


async def test_several_accountants_per_client(session: AsyncSession, client_row: Client) -> None:
    a, b = await _users(session, 2)
    session.add_all(
        [
            ClientAssignment(client_id=client_row.id, user_id=a.id),
            ClientAssignment(client_id=client_row.id, user_id=b.id),
        ]
    )
    await session.flush()


async def test_same_accountant_not_assigned_twice(
    session: AsyncSession, client_row: Client
) -> None:
    (a,) = await _users(session, 1)
    first = ClientAssignment(client_id=client_row.id, user_id=a.id)
    session.add(first)
    await session.flush()
    await _expect_rejected(session, ClientAssignment(client_id=client_row.id, user_id=a.id))


async def test_history_keeps_closed_assignments(session: AsyncSession, client_row: Client) -> None:
    (a,) = await _users(session, 1)
    now = datetime.now(UTC)
    session.add(
        ClientAssignment(
            client_id=client_row.id,
            user_id=a.id,
            assigned_at=now - timedelta(days=30),
            unassigned_at=now - timedelta(days=1),
        )
    )
    session.add(ClientAssignment(client_id=client_row.id, user_id=a.id))
    await session.flush()


async def test_unassigned_not_before_assigned(session: AsyncSession, client_row: Client) -> None:
    (a,) = await _users(session, 1)
    now = datetime.now(UTC)
    await _expect_rejected(
        session,
        ClientAssignment(
            client_id=client_row.id,
            user_id=a.id,
            assigned_at=now,
            unassigned_at=now - timedelta(days=1),
        ),
    )
