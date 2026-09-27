from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.models import DeadlineRule
from app.schemas.classifier import (
    ReportTypeCreate,
    RuleCreate,
    RuleOut,
    StatusSetCreate,
)
from app.schemas.conditions import ConditionGroup
from app.schemas.matrix import ClientReportTypeCreate

# --- Condiții ---

# Regulile din specificație (seed) trebuie să fie toate valide.
SEED_CONDITIONS: list[dict[str, Any]] = [
    {"all": [{"field": "is_vat_payer", "op": "eq", "value": True}]},
    {"all": [{"field": "has_employees", "op": "eq", "value": True}]},
    {"all": [{"field": "has_employees", "op": "eq", "value": False}]},
    {"all": [{"field": "is_it_park_resident", "op": "eq", "value": True}]},
    {},
]


@pytest.mark.parametrize("conditions", SEED_CONDITIONS)
def test_seed_conditions_valid(conditions: dict[str, Any]) -> None:
    assert ConditionGroup.model_validate(conditions).to_json() == conditions


def test_nested_conditions() -> None:
    raw = {
        "all": [
            {"field": "is_vat_payer", "op": "eq", "value": True},
            {
                "any": [
                    {"field": "legal_form", "op": "in", "value": ["SRL", "SA"]},
                    {"field": "tax_regime", "op": "is_null", "value": False},
                ]
            },
        ]
    }
    assert ConditionGroup.model_validate(raw).to_json() == raw


@pytest.mark.parametrize(
    "raw",
    [
        {"field": "tax_regime", "op": "eq", "value": None},
        {"field": "tax_regime", "op": "ne", "value": "general"},
        {"field": "legal_form", "op": "not_in", "value": ["II", "GT"]},
        {"field": "tax_regime", "op": "gte", "value": "a"},
    ],
)
def test_valid_leaves(raw: dict[str, Any]) -> None:
    ConditionGroup.model_validate({"all": [raw]})


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"field": "is_vat_payr", "op": "eq", "value": True}, "câmp necunoscut"),
        ({"field": "is_vat_payer", "op": "eq", "value": "da"}, "valoare nepermisă"),
        ({"field": "is_vat_payer", "op": "eq", "value": None}, "nu poate fi null"),
        ({"field": "has_employees", "op": "eq", "value": 1}, "valoare nepermisă"),
        ({"field": "legal_form", "op": "eq", "value": "SRLL"}, "valoare nepermisă"),
        ({"field": "legal_form", "op": "in", "value": "SRL"}, "listă nevidă"),
        ({"field": "legal_form", "op": "in", "value": []}, "listă nevidă"),
        ({"field": "has_transport", "op": "gt", "value": True}, "nu se aplică"),
        ({"field": "tax_regime", "op": "is_null", "value": "da"}, "is_null"),
        ({"field": "tax_regime", "op": "eq", "value": 5}, "valoare nepermisă"),
        ({"field": "is_vat_payer", "op": "like", "value": True}, "op"),
    ],
)
def test_invalid_leaves(raw: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        ConditionGroup.model_validate({"all": [raw]})


def test_group_cannot_have_both_all_and_any() -> None:
    with pytest.raises(ValidationError, match="nu amândouă"):
        ConditionGroup.model_validate({"all": [], "any": []})


def test_unknown_keys_rejected() -> None:
    with pytest.raises(ValidationError):
        ConditionGroup.model_validate({"al": []})


def test_rule_defaults_to_all_clients() -> None:
    rule = RuleCreate.model_validate({"name": "Toți clienții", "action": "assign"})
    assert rule.conditions.to_json() == {}


def test_rule_out_reads_jsonb_dict() -> None:
    class Row:
        id = 1
        report_type_id = 2
        name = "TVA"
        conditions = SEED_CONDITIONS[0]
        action = "assign"
        priority = 100
        is_active = True

    out = RuleOut.model_validate(Row())
    assert out.conditions.to_json() == SEED_CONDITIONS[0]


# --- Tipuri de rapoarte ---


def _rt(**kw: Any) -> ReportTypeCreate:
    fields: dict[str, Any] = {
        "category_id": 1,
        "code": "TVA12",
        "name": "Declarația TVA",
        "periodicity": "lunar",
        "deadline_rule": "day_of_next_period",
        "deadline_day": 25,
        "valid_from": "2026-01-01",
    }
    fields.update(kw)
    return ReportTypeCreate.model_validate(fields)


def test_report_type_defaults() -> None:
    rt = _rt()
    assert rt.notify_days_before == [7, 3, 1]
    assert rt.deadline_month_offset == 1
    assert rt.deadline_rule is DeadlineRule.DAY_OF_NEXT_PERIOD
    assert rt.valid_from == date(2026, 1, 1)


def test_notify_days_normalized() -> None:
    assert _rt(notify_days_before=[1, 7, 3, 7]).notify_days_before == [7, 3, 1]


@pytest.mark.parametrize("code", ["IPC21", "ITPARK_COT", "declaratii_fiscale"])
def test_codes_accepted(code: str) -> None:
    assert _rt(code=f"  {code} ").code == code


@pytest.mark.parametrize("code", ["TVA 12", "TVA-12", "", "x" * 51])
def test_codes_rejected(code: str) -> None:
    with pytest.raises(ValidationError):
        _rt(code=code)


@pytest.mark.parametrize(
    ("kw", "message"),
    [
        ({"deadline_day": None}, "cere deadline_day"),
        ({"deadline_rule": "fixed_date"}, "deadline_month"),
        ({"deadline_rule": "fixed_date", "deadline_day": 31, "deadline_month": 2}, "nu are ziua"),
        ({"deadline_day": 0}, "greater than or equal"),
        ({"valid_to": "2025-12-31"}, "valid_to"),
        ({"notify_days_before": [400]}, "less than or equal"),
        ({"deadline_month_offset": -1}, "greater than or equal"),
        ({"necunoscut": 1}, "Extra inputs"),
    ],
)
def test_report_type_rejected(kw: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _rt(**kw)


def test_fixed_date_feb_29_allowed() -> None:
    _rt(deadline_rule="fixed_date", deadline_day=29, deadline_month=2)


def test_manual_deadline_without_day() -> None:
    _rt(code="EXTRASE", deadline_rule="manual", deadline_day=None)


# --- Seturi de statusuri, matrice ---


def test_status_set_duplicate_codes() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        StatusSetCreate.model_validate(
            {
                "code": "binar",
                "name": "Binar",
                "statuses": [{"code": "efectuat", "name": "A"}, {"code": "efectuat", "name": "B"}],
            }
        )


def test_status_set_two_initials() -> None:
    with pytest.raises(ValidationError, match="un status inițial"):
        StatusSetCreate.model_validate(
            {
                "code": "binar",
                "name": "Binar",
                "statuses": [
                    {"code": "a", "name": "A", "is_initial": True},
                    {"code": "b", "name": "B", "is_initial": True},
                ],
            }
        )


def test_manual_assignment_valid_range() -> None:
    with pytest.raises(ValidationError, match="valid_to"):
        ClientReportTypeCreate(
            report_type_id=1, valid_from=date(2026, 6, 1), valid_to=date(2026, 5, 1)
        )
