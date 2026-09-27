"""Structura condițiilor din report_rules.conditions.

    {"all": [{"field": "is_vat_payer", "op": "eq", "value": true},
             {"any": [{"field": "legal_form", "op": "in", "value": ["SRL", "SA"]}, ...]}]}

`{}` înseamnă „toți clienții”. Câmpurile permise și tipul valorilor sunt în CLIENT_RULE_FIELDS;
orice altceva e refuzat la salvare, ca o regulă greșită să nu treacă neobservată.
"""

import enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.models import LegalForm


class Op(enum.StrEnum):
    EQ = "eq"
    NE = "ne"
    IN = "in"
    NOT_IN = "not_in"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IS_NULL = "is_null"


# Câmp al clientului → (tipul valorii, poate fi NULL în bază)
CLIENT_RULE_FIELDS: dict[str, tuple[type, bool]] = {
    "is_vat_payer": (bool, False),
    "is_it_park_resident": (bool, False),
    "has_employees": (bool, False),
    "has_transport": (bool, False),
    "legal_form": (LegalForm, False),
    "tax_regime": (str, True),
}

_ORDER_OPS = {Op.GT, Op.GTE, Op.LT, Op.LTE}
_LIST_OPS = {Op.IN, Op.NOT_IN}


def _check_scalar(field: str, expected: type, nullable: bool, value: Any) -> None:
    if value is None:
        if not nullable:
            raise ValueError(f"{field}: valoarea nu poate fi null")
        return
    if expected is bool:
        ok = isinstance(value, bool)
    elif issubclass(expected, enum.Enum):
        ok = value in {m.value for m in expected}
    else:
        ok = isinstance(value, expected) and not isinstance(value, bool)
    if not ok:
        raise ValueError(f"{field}: valoare nepermisă {value!r}")


class ConditionLeaf(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    op: Op
    value: Any = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.field not in CLIENT_RULE_FIELDS:
            allowed = ", ".join(CLIENT_RULE_FIELDS)
            raise ValueError(f"câmp necunoscut {self.field!r}; permise: {allowed}")
        expected, nullable = CLIENT_RULE_FIELDS[self.field]
        if self.op is Op.IS_NULL:
            if not isinstance(self.value, bool):
                raise ValueError("is_null cere value true sau false")
        elif self.op in _LIST_OPS:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError(f"{self.op} cere o listă nevidă")
            for v in self.value:
                _check_scalar(self.field, expected, nullable, v)
        else:
            if self.op in _ORDER_OPS and expected is bool:
                raise ValueError(f"{self.op} nu se aplică pe câmpul boolean {self.field}")
            _check_scalar(self.field, expected, nullable and self.op in {Op.EQ, Op.NE}, self.value)
        return self


class ConditionGroup(BaseModel):
    """`all` (ȘI) sau `any` (SAU), imbricabile. Fără niciuna: se potrivește oricărui client."""

    model_config = ConfigDict(extra="forbid")

    all: list["ConditionLeaf | ConditionGroup"] | None = None
    any: list["ConditionLeaf | ConditionGroup"] | None = None

    @model_validator(mode="after")
    def _one_kind(self) -> Self:
        if self.all is not None and self.any is not None:
            raise ValueError("un grup are fie 'all', fie 'any', nu amândouă")
        return self

    def to_json(self) -> dict[str, Any]:
        """Forma salvată în JSONB, fără cheile goale."""
        return self.model_dump(mode="json", exclude_none=True)
