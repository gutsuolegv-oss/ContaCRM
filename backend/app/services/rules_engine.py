"""Motorul de reguli: ce rapoarte i se aplică unui client.

Pentru fiecare tip de raport, regulile active se evaluează pe atributele clientului
(CLIENT_RULE_FIELDS), în ordinea priority DESC:
- dacă se potrivește cel puțin o regulă `exclude`, raportul NU se atribuie, oricare ar fi
  prioritatea regulilor `assign` (ex. IPC21: fără angajați → exclus);
- altfel, dacă se potrivește cel puțin o regulă `assign`, raportul se atribuie;
- altfel, raportul nu se atribuie.
Regula decisivă raportată e cea cu prioritatea cea mai mare dintre cele care au decis.

Funcțiile sunt pure: nu citesc și nu scriu în bază. Regulile le încarcă repository-ul, iar
reconcilierea cu client_report_types o face serviciul matricei.
"""

import enum
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from app.models import RuleAction
from app.schemas.conditions import CLIENT_RULE_FIELDS, ConditionGroup, ConditionLeaf, Op


class RuleError(Exception):
    """Condițiile unei reguli din bază nu sunt valide (au fost modificate ocolind API-ul)."""


class RuleLike(Protocol):
    @property
    def id(self) -> int: ...
    @property
    def report_type_id(self) -> int: ...
    @property
    def action(self) -> RuleAction: ...
    @property
    def priority(self) -> int: ...
    @property
    def is_active(self) -> bool: ...
    @property
    def conditions(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class Decision:
    report_type_id: int
    assigned: bool
    rule_id: int  # regula decisivă
    action: RuleAction


def client_attributes(client: object) -> dict[str, Any]:
    """Valorile câmpurilor pe care se evaluează regulile. Enum-urile devin text."""
    values = {}
    for name in CLIENT_RULE_FIELDS:
        value = getattr(client, name)
        values[name] = value.value if isinstance(value, enum.Enum) else value
    return values


def _compare(op: Op, actual: Any, expected: Any) -> bool:
    if op is Op.IS_NULL:
        return (actual is None) is bool(expected)
    if op is Op.EQ:
        return bool(actual == expected)
    if op is Op.NE:
        return bool(actual != expected)
    if op is Op.IN:
        return actual in expected
    if op is Op.NOT_IN:
        return actual not in expected
    # gt/gte/lt/lte: o valoare lipsă (NULL) nu se potrivește niciodată
    if actual is None:
        return False
    if op is Op.GT:
        return bool(actual > expected)
    if op is Op.GTE:
        return bool(actual >= expected)
    if op is Op.LT:
        return bool(actual < expected)
    return bool(actual <= expected)


def matches(node: ConditionGroup | ConditionLeaf, attrs: Mapping[str, Any]) -> bool:
    if isinstance(node, ConditionLeaf):
        return _compare(node.op, attrs[node.field], node.value)
    if node.all is not None:
        return all(matches(child, attrs) for child in node.all)
    if node.any is not None:
        return any(matches(child, attrs) for child in node.any)
    return True  # {}: toți clienții


def parse_conditions(rule: RuleLike) -> ConditionGroup:
    try:
        return ConditionGroup.model_validate(dict(rule.conditions))
    except ValidationError as e:
        raise RuleError(f"regula {rule.id}: condiții invalide: {e}") from e


def decide_client_reports(client: object, rules: Iterable[RuleLike]) -> dict[int, Decision]:
    """Decizia pentru fiecare tip de raport care are cel puțin o regulă potrivită."""
    attrs = client_attributes(client)
    active = sorted((r for r in rules if r.is_active), key=lambda r: (-r.priority, r.id))
    assign: dict[int, RuleLike] = {}
    exclude: dict[int, RuleLike] = {}
    for rule in active:
        if not matches(parse_conditions(rule), attrs):
            continue
        target = exclude if rule.action is RuleAction.EXCLUDE else assign
        target.setdefault(rule.report_type_id, rule)  # prima = prioritatea cea mai mare

    decisions = {
        rt: Decision(rt, assigned=True, rule_id=r.id, action=RuleAction.ASSIGN)
        for rt, r in assign.items()
    }
    for rt, r in exclude.items():
        decisions[rt] = Decision(rt, assigned=False, rule_id=r.id, action=RuleAction.EXCLUDE)
    return decisions


def evaluate_client_reports(client: object, rules: Iterable[RuleLike]) -> list[int]:
    """ID-urile tipurilor de rapoarte care i se aplică clientului, crescător."""
    decisions = decide_client_reports(client, rules)
    return sorted(rt for rt, d in decisions.items() if d.assigned)
