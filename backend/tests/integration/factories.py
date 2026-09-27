"""Date de test comune: clasificator minimal (ca în seed), clienți, utilizatori."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Client,
    ClientAssignment,
    DeadlineRule,
    LegalForm,
    Organization,
    Periodicity,
    ReportCategory,
    ReportRule,
    ReportType,
    RuleAction,
    User,
    UserRole,
)

VALID_FROM = date(2026, 1, 1)


def eq(name: str, value: Any) -> dict[str, Any]:
    return {"all": [{"field": name, "op": "eq", "value": value}]}


@dataclass
class Classifier:
    category: ReportCategory
    types: dict[str, ReportType]

    def id(self, code: str) -> int:
        return self.types[code].id


async def make_classifier(session: AsyncSession) -> Classifier:
    """TVA12, IPC21, TL13 (fără reguli), EXTRASE (toți clienții), cu regulile din seed."""
    category = ReportCategory(code="declaratii_fiscale", name="Declarații fiscale")
    session.add(category)
    await session.flush()
    types = {
        code: ReportType(
            category_id=category.id,
            code=code,
            name=code,
            periodicity=periodicity,
            deadline_rule=DeadlineRule.DAY_OF_NEXT_PERIOD,
            deadline_day=25,
            valid_from=VALID_FROM,
        )
        for code, periodicity in [
            ("TVA12", Periodicity.LUNAR),
            ("IPC21", Periodicity.LUNAR),
            ("TL13", Periodicity.SEMESTRIAL),
            ("EXTRASE", Periodicity.LUNAR),
        ]
    }
    session.add_all(types.values())
    await session.flush()
    session.add_all(
        [
            ReportRule(
                report_type_id=types["TVA12"].id,
                name="Plătitori TVA",
                action=RuleAction.ASSIGN,
                conditions=eq("is_vat_payer", True),
            ),
            ReportRule(
                report_type_id=types["IPC21"].id,
                name="Cu angajați",
                action=RuleAction.ASSIGN,
                conditions=eq("has_employees", True),
            ),
            ReportRule(
                report_type_id=types["IPC21"].id,
                name="Fără angajați",
                action=RuleAction.EXCLUDE,
                priority=200,
                conditions=eq("has_employees", False),
            ),
            ReportRule(
                report_type_id=types["EXTRASE"].id,
                name="Toți clienții",
                action=RuleAction.ASSIGN,
                priority=50,
            ),
        ]
    )
    await session.flush()
    return Classifier(category, types)


async def make_client(session: AsyncSession, idno: str = "1003600012345", **kw: Any) -> Client:
    fields: dict[str, Any] = {"name": f"Client {idno[-4:]}", "legal_form": LegalForm.SRL}
    fields.update(kw)
    client = Client(idno=idno, **fields)
    session.add(client)
    await session.flush()
    return client


async def make_user(
    session: AsyncSession,
    email: str,
    role: UserRole,
    password_hash: str = "x",  # noqa: S107
) -> User:
    org = await session.get(Organization, 1)
    if org is None:
        org = Organization(name="Birou")
        session.add(org)
        await session.flush()
    user = User(
        organization_id=org.id,
        email=email,
        full_name=email.split("@")[0],
        password_hash=password_hash,
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


async def assign(session: AsyncSession, client: Client, user: User) -> None:
    session.add(ClientAssignment(client_id=client.id, user_id=user.id))
    await session.flush()
