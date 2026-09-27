import pytest
from pydantic import ValidationError

from app.schemas.clients import BankAccountCreate, BankAccountUpdate, ClientCreate


@pytest.mark.parametrize(
    "raw",
    ["MD24AG000000022512345678", "md24 ag00 0000 0225 1234 5678", " MD24AG00\t0000022512345678 "],
)
def test_iban_normalized(raw: str) -> None:
    account = BankAccountCreate(bank_name="MAIB", iban=raw)
    assert account.iban == "MD24AG000000022512345678"
    assert account.currency == "MDL"


@pytest.mark.parametrize(
    "raw", ["RO49AAAA1B31007593840000", "MD24AG00000002251234567", "MD2XAG000000022512345678"]
)
def test_iban_rejected(raw: str) -> None:
    with pytest.raises(ValidationError, match="IBAN"):
        BankAccountCreate(bank_name="MAIB", iban=raw)


def test_iban_update_optional() -> None:
    assert BankAccountUpdate(bank_name="MAIB").iban is None
    assert (
        BankAccountUpdate(iban="md24 ag00 0000 0225 1234 5678").iban == "MD24AG000000022512345678"
    )


def test_currency_uppercased() -> None:
    assert (
        BankAccountCreate(bank_name="X", iban="MD24AG000000022512345678", currency="eur").currency
        == "EUR"
    )


@pytest.mark.parametrize("idno", ["123", "10036000123456", "100360001234A"])
def test_idno_format(idno: str) -> None:
    with pytest.raises(ValidationError):
        ClientCreate.model_validate({"name": "X", "idno": idno, "legal_form": "SRL"})


def test_vat_code_needs_vat_payer() -> None:
    base = {"name": "X", "idno": "1003600012345", "legal_form": "SRL", "vat_code": "0600012"}
    with pytest.raises(ValidationError, match="plătitorii de TVA"):
        ClientCreate.model_validate(base)
    assert ClientCreate.model_validate({**base, "is_vat_payer": True}).vat_code == "0600012"
