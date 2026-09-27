from dataclasses import dataclass, field
from typing import Any

import pytest

from app.models import Client, LegalForm, RuleAction
from app.schemas.conditions import ConditionGroup
from app.services.rules_engine import (
    RuleError,
    client_attributes,
    decide_client_reports,
    evaluate_client_reports,
    matches,
)

# ID-uri de tipuri de raport, ca în seed
TVA12, IPC21, IU17, ITPARK_COT, FACT_LIVR, FACT_PROC, EXTRASE, TL13 = range(1, 9)


@dataclass
class Rule:
    id: int
    report_type_id: int
    action: RuleAction
    priority: int
    conditions: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True


def eq(name: str, value: Any) -> dict[str, Any]:
    return {"all": [{"field": name, "op": "eq", "value": value}]}


# Regulile de aplicabilitate din specificație
SEED_RULES = [
    Rule(1, TVA12, RuleAction.ASSIGN, 100, eq("is_vat_payer", True)),
    Rule(2, IPC21, RuleAction.ASSIGN, 100, eq("has_employees", True)),
    Rule(3, IPC21, RuleAction.EXCLUDE, 200, eq("has_employees", False)),
    Rule(4, IU17, RuleAction.ASSIGN, 100, eq("is_it_park_resident", True)),
    Rule(5, ITPARK_COT, RuleAction.ASSIGN, 100, eq("is_it_park_resident", True)),
    Rule(6, FACT_LIVR, RuleAction.ASSIGN, 50),
    Rule(7, FACT_PROC, RuleAction.ASSIGN, 50),
    Rule(8, EXTRASE, RuleAction.ASSIGN, 50),
]
ALWAYS = [FACT_LIVR, FACT_PROC, EXTRASE]


def make_client(**kw: Any) -> Client:
    fields: dict[str, Any] = {
        "name": "Test SRL",
        "idno": "1000000000001",
        "legal_form": LegalForm.SRL,
        "is_vat_payer": False,
        "is_it_park_resident": False,
        "has_employees": False,
        "has_transport": False,
        "tax_regime": None,
    }
    fields.update(kw)
    return Client(**fields)


# --- Scenariile din specificație ---


def test_vat_payer_with_employees() -> None:
    client = make_client(is_vat_payer=True, has_employees=True)
    assert evaluate_client_reports(client, SEED_RULES) == sorted([TVA12, IPC21, *ALWAYS])


def test_without_employees_ipc21_excluded() -> None:
    client = make_client(is_vat_payer=True, has_employees=False)
    decisions = decide_client_reports(client, SEED_RULES)
    assert decisions[IPC21].assigned is False
    assert decisions[IPC21].rule_id == 3
    assert evaluate_client_reports(client, SEED_RULES) == sorted([TVA12, *ALWAYS])


def test_it_park_resident() -> None:
    client = make_client(is_it_park_resident=True, has_employees=True)
    assert evaluate_client_reports(client, SEED_RULES) == sorted([IPC21, IU17, ITPARK_COT, *ALWAYS])


def test_minimal_client_gets_only_primary_documents() -> None:
    assert evaluate_client_reports(make_client(), SEED_RULES) == ALWAYS


def test_report_without_rules_is_never_assigned() -> None:
    # TL13 și POLMED25 n-au reguli: se atribuie doar manual
    client = make_client(is_vat_payer=True, has_employees=True, is_it_park_resident=True)
    assert TL13 not in evaluate_client_reports(client, SEED_RULES)


# --- Prioritate, exclude, reguli inactive ---


def test_exclude_wins_even_with_lower_priority() -> None:
    rules = [
        Rule(1, TVA12, RuleAction.ASSIGN, 500),
        Rule(2, TVA12, RuleAction.EXCLUDE, 10, eq("legal_form", "II")),
    ]
    assert evaluate_client_reports(make_client(legal_form=LegalForm.II), rules) == []
    assert evaluate_client_reports(make_client(legal_form=LegalForm.SRL), rules) == [TVA12]


def test_decisive_rule_is_highest_priority() -> None:
    rules = [
        Rule(1, TVA12, RuleAction.ASSIGN, 50),
        Rule(2, TVA12, RuleAction.ASSIGN, 150),
        Rule(3, TVA12, RuleAction.ASSIGN, 150),  # egalitate: ID-ul mai mic
    ]
    assert decide_client_reports(make_client(), rules)[TVA12].rule_id == 2


def test_inactive_rules_ignored() -> None:
    rules = [
        Rule(1, TVA12, RuleAction.ASSIGN, 100),
        Rule(2, TVA12, RuleAction.EXCLUDE, 200, is_active=False),
    ]
    assert evaluate_client_reports(make_client(), rules) == [TVA12]


def test_no_rules() -> None:
    assert evaluate_client_reports(make_client(), []) == []
    assert decide_client_reports(make_client(), []) == {}


def test_invalid_conditions_in_db_raise() -> None:
    rules = [Rule(9, TVA12, RuleAction.ASSIGN, 100, eq("camp_inexistent", True))]
    with pytest.raises(RuleError, match="regula 9"):
        evaluate_client_reports(make_client(), rules)


# --- Operatori și grupuri ---


def check(raw: dict[str, Any], **client: Any) -> bool:
    return matches(ConditionGroup.model_validate(raw), client_attributes(make_client(**client)))


def leaf(name: str, op: str, value: Any) -> dict[str, Any]:
    return {"all": [{"field": name, "op": op, "value": value}]}


@pytest.mark.parametrize(
    ("op", "value", "legal_form", "expected"),
    [
        ("eq", "SRL", LegalForm.SRL, True),
        ("eq", "SA", LegalForm.SRL, False),
        ("ne", "SA", LegalForm.SRL, True),
        ("in", ["SRL", "SA"], LegalForm.SA, True),
        ("in", ["SRL", "SA"], LegalForm.II, False),
        ("not_in", ["II", "GT"], LegalForm.II, False),
        ("not_in", ["II", "GT"], LegalForm.ONG, True),
    ],
)
def test_enum_operators(op: str, value: Any, legal_form: LegalForm, expected: bool) -> None:
    assert check(leaf("legal_form", op, value), legal_form=legal_form) is expected


@pytest.mark.parametrize(
    ("op", "value", "tax_regime", "expected"),
    [
        ("is_null", True, None, True),
        ("is_null", True, "general", False),
        ("is_null", False, "general", True),
        ("eq", None, None, True),
        ("ne", None, "general", True),
        ("gt", "a", None, False),  # NULL nu se compară
        ("gt", "a", "b", True),
        ("gte", "b", "b", True),
        ("lt", "b", "a", True),
        ("lte", "a", "b", False),
    ],
)
def test_nullable_and_order_operators(
    op: str, value: Any, tax_regime: str | None, expected: bool
) -> None:
    assert check(leaf("tax_regime", op, value), tax_regime=tax_regime) is expected


def test_nested_groups() -> None:
    # plătitor TVA ȘI (SRL SAU are angajați)
    raw = {
        "all": [
            {"field": "is_vat_payer", "op": "eq", "value": True},
            {
                "any": [
                    {"field": "legal_form", "op": "eq", "value": "SRL"},
                    {"field": "has_employees", "op": "eq", "value": True},
                ]
            },
        ]
    }
    assert check(raw, is_vat_payer=True, legal_form=LegalForm.SRL) is True
    assert check(raw, is_vat_payer=True, legal_form=LegalForm.II, has_employees=True) is True
    assert check(raw, is_vat_payer=True, legal_form=LegalForm.II) is False
    assert check(raw, is_vat_payer=False, legal_form=LegalForm.SRL) is False


def test_empty_groups() -> None:
    assert check({}) is True
    assert check({"all": []}) is True
    assert check({"any": []}) is False
