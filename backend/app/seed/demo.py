"""Date demonstrative pentru DEZVOLTARE: utilizatori, clienții din mockup, grilele pe
august și septembrie 2026, parțial completate.

    python -m app.seed.demo

Refuză să ruleze în producție (ENVIRONMENT=prod). Rulează și seed-ul clasificatorului, dacă
lipsește. Dacă datele demo există deja (admin@birou.md), nu face nimic.
Toți utilizatorii au parola DEMO_PASSWORD.
"""

import asyncio
import sys
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import get_sessionmaker
from app.models import (
    ClientStatus,
    LegalForm,
    Organization,
    ReportEntry,
    ReportEntryStep,
    Status,
    User,
    UserRole,
)
from app.repositories.execution import PeriodRepository
from app.schemas.clients import BankAccountCreate, ClientCreate, ClientUpdate, ContactCreate
from app.seed.classifier import seed_classifier
from app.services.clients import ClientService
from app.services.grid import GridService

DEMO_PASSWORD = "demo-parola-2026"  # noqa: S105  # doar pentru dezvoltare
OBLIGATIONS_FROM = date(2026, 1, 1)

ACCOUNTANTS = [
    ("ana.rusu", "Ana Rusu"),
    ("ion.ceban", "Ion Ceban"),
    ("maria.lungu", "Maria Lungu"),
    ("victor.popa", "Victor Popa"),
]

# (denumire, IDNO, plătitor TVA, formă, contabil 1-4 sau None, localitate, în onboarding)
CLIENTS = [
    ("Agro-Nord SRL", "1003600012345", True, "SRL", 1, "Bălți", False),
    ("Vinăria Codru SA", "1002600054321", True, "SA", 2, "Chișinău", False),
    ("ÎI Moraru Petru", "1010600023456", False, "II", 1, "Orhei", False),
    ("TechSoft Solutions SRL", "1015600034567", True, "SRL", 3, "Chișinău", False),
    ("Mobila Lux SRL", "1008600045678", False, "SRL", 2, "Ungheni", False),
    ("Farmacia Sănătate SRL", "1012600056789", True, "SRL", 4, "Cahul", False),
    ("Construct-Grup SRL", "1006600067890", True, "SRL", 1, "Chișinău", False),
    ("Cafeneaua Aroma SRL", "1019600078901", False, "SRL", 3, "Chișinău", False),
    ("Transavto Logistic SRL", "1004600089012", True, "SRL", 4, "Comrat", False),
    ("ÎI Ciobanu Elena", "1021600090123", False, "II", None, "Soroca", True),
    ("Dental Art SRL", "1017600001234", False, "SRL", 2, "Chișinău", False),
    ("Moldagro Export SA", "1001600011223", True, "SA", 3, "Edineț", False),
    ("Print Studio SRL", "1022600022334", False, "SRL", None, "Chișinău", True),
    ("Eco Fructe SRL", "1011600033445", True, "SRL", 1, "Criuleni", False),
]


async def _users(session: AsyncSession) -> tuple[User, list[User]]:
    org = await session.scalar(select(Organization).order_by(Organization.id).limit(1))
    if org is None:
        org = Organization(name="Birou de contabilitate (demo)")
        session.add(org)
        await session.flush()
    password_hash = hash_password(DEMO_PASSWORD)

    def user(username: str, name: str, role: UserRole) -> User:
        return User(
            organization_id=org.id,
            username=username,
            full_name=name,
            role=role,
            password_hash=password_hash,
        )

    admin = user("admin", "Administrator", UserRole.ADMIN)
    director = user("director", "Elena Director", UserRole.DIRECTOR)
    accountants = [user(username, name, UserRole.CONTABIL) for username, name in ACCOUNTANTS]
    session.add_all([admin, director, *accountants])
    await session.commit()
    return admin, accountants


async def _clients(session: AsyncSession, admin: User, accountants: list[User]) -> None:
    service = ClientService(session, admin)
    for i, (name, idno, vat, form, acc, city, onboarding) in enumerate(CLIENTS, start=1):
        client, _ = await service.create(
            ClientCreate(
                name=name,
                idno=idno,
                legal_form=LegalForm(form),
                is_vat_payer=vat,
                has_employees=form != "II",
                is_it_park_resident=name.startswith("TechSoft"),
                has_transport=name.startswith("Transavto"),
                locality=city,
            ),
            OBLIGATIONS_FROM,
        )
        if not onboarding:
            await service.update(
                client.id, ClientUpdate(client_status=ClientStatus.ACTIVE), OBLIGATIONS_FROM
            )
        if acc is not None:
            await service.assign(client.id, accountants[acc - 1].id)
        await service.add_bank_account(
            client.id,
            BankAccountCreate(
                bank_name="MAIB", iban=f"MD24AG0000000225{idno[-8:]}", is_primary=True
            ),
        )
        await service.add_contact(
            client.id,
            ContactCreate(
                full_name=f"Administrator {name.split()[0]}",
                position="Administrator",
                is_primary=True,
                phone=f"+373 69 {100 + i:03d} {200 + i * 3:03d}",
            ),
        )


async def _work(session: AsyncSession, admin: User) -> None:
    """August: aproape totul depus (câteva restanțe). Septembrie: început."""
    grid = GridService(session, admin)
    finals = dict(
        (await session.execute(select(Status.status_set_id, Status.id).where(Status.is_final)))
        .tuples()
        .all()
    )
    for month, every_nth_open in ((8, 7), (9, 2)):
        await grid.generate(2026, month)
        periods = await PeriodRepository(session).list_ending_in(2026, month)
        entries = (
            await session.scalars(
                select(ReportEntry)
                .where(ReportEntry.period_id.in_([p.id for p in periods]))
                .options(selectinload(ReportEntry.steps).selectinload(ReportEntryStep.step))
                .order_by(ReportEntry.id)
            )
        ).all()
        now = datetime(2026, month + 1, 20, 12, 0, tzinfo=UTC)
        for n, entry in enumerate(entries):
            if n % every_nth_open == 0:
                continue  # rămâne deschis
            for step in entry.steps:
                await grid.set_step_status(
                    entry.id, step.step_id, finals[step.step.status_set_id], now
                )


async def main() -> None:
    if get_settings().environment == "prod":
        sys.exit("Datele demo nu se încarcă în producție.")
    async with get_sessionmaker()() as session:
        await seed_classifier(session)
        if await session.scalar(select(User).where(User.username == "admin")):
            print("Datele demo există deja (utilizatorul admin). Nu am modificat nimic.")
            return
        admin, accountants = await _users(session)
        await _clients(session, admin, accountants)
        await _work(session, admin)
    print("Date demo încărcate. Utilizatori (parola pentru toți: " + DEMO_PASSWORD + "):")
    print("  admin (admin), director (director)")
    for username, name in ACCOUNTANTS:
        print(f"  {username} (contabil, {name})")


if __name__ == "__main__":
    asyncio.run(main())
