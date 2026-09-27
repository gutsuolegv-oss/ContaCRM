from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Client,
    DeadlineRule,
    LegalForm,
    Periodicity,
    ReportCategory,
    ReportRule,
    ReportType,
    RuleAction,
)
from app.services.rules_engine import evaluate_client_reports


async def test_engine_on_rows_from_db(session: AsyncSession) -> None:
    cat = ReportCategory(code="declaratii_fiscale", name="Declarații fiscale")
    session.add(cat)
    await session.flush()
    types = {
        code: ReportType(
            category_id=cat.id,
            code=code,
            name=code,
            periodicity=Periodicity.LUNAR,
            deadline_rule=DeadlineRule.DAY_OF_NEXT_PERIOD,
            deadline_day=25,
            valid_from=date(2026, 1, 1),
        )
        for code in ("TVA12", "IPC21", "EXTRASE")
    }
    session.add_all(types.values())
    await session.flush()

    def cond(name: str, value: object) -> dict[str, object]:
        return {"all": [{"field": name, "op": "eq", "value": value}]}

    session.add_all(
        [
            ReportRule(
                report_type_id=types["TVA12"].id,
                name="TVA",
                action=RuleAction.ASSIGN,
                conditions=cond("is_vat_payer", True),
            ),
            ReportRule(
                report_type_id=types["IPC21"].id,
                name="Angajați",
                action=RuleAction.ASSIGN,
                conditions=cond("has_employees", True),
            ),
            ReportRule(
                report_type_id=types["IPC21"].id,
                name="Fără angajați",
                priority=200,
                action=RuleAction.EXCLUDE,
                conditions=cond("has_employees", False),
            ),
            ReportRule(
                report_type_id=types["EXTRASE"].id,
                name="Toți",
                priority=50,
                action=RuleAction.ASSIGN,
            ),
            ReportRule(
                report_type_id=types["TVA12"].id,
                name="Doar SA (inactivă)",
                is_active=False,
                action=RuleAction.EXCLUDE,
                conditions={"all": [{"field": "legal_form", "op": "in", "value": ["SRL"]}]},
            ),
        ]
    )
    session.add(
        Client(
            name="Agro-Nord SRL", idno="1003600012345", legal_form=LegalForm.SRL, is_vat_payer=True
        )
    )
    await session.flush()
    expected = sorted([types["TVA12"].id, types["EXTRASE"].id])
    session.expire_all()  # recitește totul din bază (JSONB, enum, valori implicite)

    client = (await session.scalars(select(Client))).one()
    rules = (await session.scalars(select(ReportRule))).all()
    assert client.has_employees is False  # valoarea implicită din bază
    assert evaluate_client_reports(client, rules) == expected
