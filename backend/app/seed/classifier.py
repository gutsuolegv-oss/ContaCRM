"""Datele inițiale ale clasificatorului de rapoarte și sărbătorile pe 2026.

    python -m app.seed.classifier

Se poate rula de mai multe ori: creează doar ce lipsește și NU suprascrie rândurile existente
(modificările făcute între timp din interfață rămân). Fiecare rând creat intră în audit_log,
cu utilizator gol (acțiune a sistemului).

Paștele ortodox și Paștele Blajinilor (date variabile) nu sunt incluse: se adaugă manual.
"""

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.session import get_sessionmaker
from app.models import (
    DeadlineRule,
    Holiday,
    Periodicity,
    ReportCategory,
    ReportRule,
    ReportType,
    ReportTypeStep,
    RuleAction,
    Status,
    StatusSet,
)
from app.services.audit import AuditService

VALID_FROM = date(2026, 1, 1)

# (cod, denumire, [(cod status, denumire, inițial, final)])
STATUS_SETS = [
    ("depunere", "Depunere", [
        ("neinceput", "Neînceput", True, False),
        ("transmis", "Transmis", False, False),
        ("incarcat", "Încărcat", False, True),
    ]),
    ("plata", "Plată", [
        ("neachitat", "Neachitat", True, False),
        ("anuntat", "Anunțat", False, False),
        ("achitat", "Achitat", False, True),
    ]),
    ("binar", "Efectuare", [
        ("neefectuat", "Neefectuat", True, False),
        ("efectuat", "Efectuat", False, True),
    ]),
]  # fmt: skip

CATEGORIES = [
    ("declaratii_fiscale", "Declarații fiscale", 10),
    ("plati_impozite", "Plăți și impozite", 20),
    ("rapoarte_speciale", "Rapoarte speciale", 30),
    ("documente_primare", "Documente primare", 40),
]

# Etape: (cod, denumire, set de statusuri)
TRANSMITERE = ("transmitere", "Transmitere", "depunere")
INREGISTRARE_1C = ("inregistrare_1c", "Înregistrare în 1C", "binar")
PLATA = ("plata", "Plată", "plata")
EFECTUARE = ("efectuare", "Efectuare", "binar")


def _eq(name: str, value: Any) -> dict[str, Any]:
    return {"all": [{"field": name, "op": "eq", "value": value}]}


# (denumire, acțiune, prioritate, condiții)
RuleSeed = tuple[str, RuleAction, int, dict[str, Any]]


@dataclass
class ReportTypeSeed:
    code: str
    name: str
    category: str
    authority: str
    steps: list[tuple[str, str, str]]
    full_name: str | None = None
    legal_reference: str | None = None
    periodicity: Periodicity = Periodicity.LUNAR
    deadline_day: int | None = 25
    requires_payment: bool = False
    rules: list[RuleSeed] = field(default_factory=list)

    @property
    def deadline_rule(self) -> DeadlineRule:
        return DeadlineRule.MANUAL if self.deadline_day is None else DeadlineRule.DAY_OF_NEXT_PERIOD


ALL_CLIENTS: list[RuleSeed] = [("Toți clienții", RuleAction.ASSIGN, 50, {})]
IT_PARK: list[RuleSeed] = [
    ("Rezident IT Park", RuleAction.ASSIGN, 100, _eq("is_it_park_resident", True))
]

REPORT_TYPES = [
    ReportTypeSeed(
        code="IPC21",
        name="Darea de seamă IPC21",
        full_name=(
            "Darea de seamă privind reținerea impozitului pe venit, a primelor de asigurare "
            "obligatorie de asistență medicală și a contribuțiilor de asigurări sociale de stat "
            "obligatorii calculate"
        ),
        category="declaratii_fiscale",
        authority="SFS/CNAS",
        legal_reference="OMF nr.94 din 30.07.2020",
        steps=[TRANSMITERE],
        # Angajatorii care în luna de gestiune nu fac plăți în folosul persoanelor fizice,
        # nu calculează contribuții și nu au angajați nu prezintă darea de seamă: de aceea
        # regula exclude are prioritate mai mare.
        rules=[
            ("Are angajați", RuleAction.ASSIGN, 100, _eq("has_employees", True)),
            ("Fără angajați", RuleAction.EXCLUDE, 200, _eq("has_employees", False)),
        ],
    ),
    ReportTypeSeed(
        code="TVA12",
        name="Declarația TVA12",
        full_name="Declarația privind taxa pe valoarea adăugată",
        category="declaratii_fiscale",
        authority="SFS",
        legal_reference="Codul fiscal, Titlul III",
        steps=[TRANSMITERE],
        rules=[("Plătitori de TVA", RuleAction.ASSIGN, 100, _eq("is_vat_payer", True))],
    ),
    ReportTypeSeed(
        code="IU17",
        name="Declarația IU17",
        full_name=(
            "Declarația cu privire la impozitul unic al rezidenților parcurilor pentru "
            "tehnologia informației"
        ),
        category="declaratii_fiscale",
        authority="SFS",
        legal_reference="Codul fiscal, Titlul X",
        steps=[TRANSMITERE, INREGISTRARE_1C],
        rules=IT_PARK,
    ),
    ReportTypeSeed(
        code="TL13",
        name="Darea de seamă TL13",
        full_name="Darea de seamă pe taxele locale",
        category="declaratii_fiscale",
        authority="SFS",
        legal_reference="Ordinul IFPS nr.1603 din 20.12.2012",
        periodicity=Periodicity.SEMESTRIAL,
        steps=[TRANSMITERE, INREGISTRARE_1C],
        # fără reguli: se atribuie manual până se clarifică criteriile
    ),
    ReportTypeSeed(
        code="POLMED25",
        name="Darea de seamă POLMED25",
        full_name=(
            "Darea de seamă privind taxa pentru mărfurile care, în procesul utilizării, "
            "cauzează poluarea mediului"
        ),
        category="declaratii_fiscale",
        authority="SFS",
        legal_reference="Ministerul Finanțelor; a înlocuit POLMED23",
        steps=[TRANSMITERE, INREGISTRARE_1C],
        # fără reguli: se atribuie manual până se clarifică criteriile
    ),
    ReportTypeSeed(
        code="ITPARK_COT",
        name="Cotizația IT Park",
        full_name="Cotizația de rezident Moldova IT Park",
        category="rapoarte_speciale",
        authority="Administrația MITP",
        legal_reference="Contract de rezident",
        deadline_day=20,
        requires_payment=True,
        steps=[PLATA],
        rules=IT_PARK,
    ),
    ReportTypeSeed(
        code="FACT_LIVR",
        name="Facturi livrări",
        category="documente_primare",
        authority="intern",
        deadline_day=None,
        steps=[EFECTUARE],
        rules=ALL_CLIENTS,
    ),
    ReportTypeSeed(
        code="FACT_PROC",
        name="Facturi procurare",
        category="documente_primare",
        authority="intern",
        deadline_day=None,
        steps=[EFECTUARE],
        rules=ALL_CLIENTS,
    ),
    ReportTypeSeed(
        code="EXTRASE",
        name="Extrase bancare",
        category="documente_primare",
        authority="intern",
        deadline_day=None,
        steps=[EFECTUARE],
        rules=ALL_CLIENTS,
    ),
]

HOLIDAYS_2026 = [
    (date(2026, 1, 1), "Anul Nou"),
    (date(2026, 1, 7), "Nașterea lui Isus Hristos (Crăciunul pe stil vechi)"),
    (date(2026, 1, 8), "Nașterea lui Isus Hristos (Crăciunul pe stil vechi)"),
    (date(2026, 3, 8), "Ziua internațională a femeii"),
    (date(2026, 5, 1), "Ziua internațională a solidarității oamenilor muncii"),
    (date(2026, 5, 9), "Ziua Victoriei"),
    (date(2026, 6, 1), "Ziua Ocrotirii Copilului"),
    (date(2026, 8, 27), "Ziua Independenței"),
    (date(2026, 8, 31), "Sărbătoarea „Limba noastră”"),
    (date(2026, 12, 25), "Nașterea lui Isus Hristos (Crăciunul pe stil nou)"),
]


T = TypeVar("T", bound=Base)


@dataclass
class SeedReport:
    created: Counter[str] = field(default_factory=Counter)
    existing: Counter[str] = field(default_factory=Counter)

    def __str__(self) -> str:
        tables = sorted(set(self.created) | set(self.existing))
        return "\n".join(
            f"{t:<20} create: {self.created[t]:>3}   existau deja: {self.existing[t]:>3}"
            for t in tables
        )


class _Seeder:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session, None)
        self.report = SeedReport()

    async def get_or_create(
        self, model: type[T], lookup: dict[str, Any], values: dict[str, Any] | None = None
    ) -> T:
        """Rândul găsit după `lookup` (neschimbat), sau unul nou cu `lookup` + `values`."""
        table = model.__tablename__
        found = await self.session.scalar(select(model).filter_by(**lookup))
        if found is not None:
            self.report.existing[table] += 1
            return found
        obj = model(**lookup, **(values or {}))
        self.session.add(obj)
        await self.session.flush()
        self.audit.created(obj)
        self.report.created[table] += 1
        return obj

    async def run(self) -> SeedReport:
        status_sets: dict[str, StatusSet] = {}
        for set_code, set_name, statuses in STATUS_SETS:
            status_set = await self.get_or_create(StatusSet, {"code": set_code}, {"name": set_name})
            status_sets[set_code] = status_set
            for order, (code, name, is_initial, is_final) in enumerate(statuses, start=1):
                await self.get_or_create(
                    Status,
                    {"status_set_id": status_set.id, "code": code},
                    {
                        "name": name,
                        "is_initial": is_initial,
                        "is_final": is_final,
                        "sort_order": order,
                    },
                )

        categories: dict[str, ReportCategory] = {}
        for code, name, sort_order in CATEGORIES:
            categories[code] = await self.get_or_create(
                ReportCategory, {"code": code}, {"name": name, "sort_order": sort_order}
            )

        for order, rt in enumerate(REPORT_TYPES, start=1):
            report_type = await self.get_or_create(
                ReportType,
                {"code": rt.code, "valid_from": VALID_FROM},
                {
                    "category_id": categories[rt.category].id,
                    "name": rt.name,
                    "full_name": rt.full_name,
                    "legal_reference": rt.legal_reference,
                    "authority": rt.authority,
                    "periodicity": rt.periodicity,
                    "deadline_rule": rt.deadline_rule,
                    "deadline_day": rt.deadline_day,
                    "requires_payment": rt.requires_payment,
                    "sort_order": order * 10,
                },
            )
            for step_order, (code, name, set_code) in enumerate(rt.steps, start=1):
                await self.get_or_create(
                    ReportTypeStep,
                    {"report_type_id": report_type.id, "code": code},
                    {
                        "name": name,
                        "status_set_id": status_sets[set_code].id,
                        "sort_order": step_order,
                    },
                )
            for name, action, priority, conditions in rt.rules:
                await self.get_or_create(
                    ReportRule,
                    {"report_type_id": report_type.id, "name": name},
                    {"action": action, "priority": priority, "conditions": conditions},
                )

        for day, name in HOLIDAYS_2026:
            await self.get_or_create(Holiday, {"holiday_date": day}, {"name": name})

        return self.report


async def seed_classifier(session: AsyncSession) -> SeedReport:
    report = await _Seeder(session).run()
    await session.commit()
    return report


async def _main() -> None:
    async with get_sessionmaker()() as session:
        print(await seed_classifier(session))


if __name__ == "__main__":
    asyncio.run(_main())
