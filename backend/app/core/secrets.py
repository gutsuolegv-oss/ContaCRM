"""Criptarea secretelor păstrate în bază (ex. tokenul botului Telegram).

Cheia se derivă din APP_SECRET_KEY: cine are doar o copie a bazei nu poate citi secretele.
Dacă APP_SECRET_KEY se schimbă, secretele vechi nu se mai pot descifra și trebuie introduse
din nou (în Setări).
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet(purpose: str) -> Fernet:
    secret = get_settings().app_secret_key.get_secret_value().encode()
    key = hashlib.sha256(b"contacrm:" + purpose.encode() + b":" + secret).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str, purpose: str) -> str:
    return _fernet(purpose).encrypt(value.encode()).decode()


def decrypt(value: str, purpose: str) -> str | None:
    """`None` dacă nu se poate descifra (ex. APP_SECRET_KEY s-a schimbat)."""
    try:
        return _fernet(purpose).decrypt(value.encode()).decode()
    except InvalidToken:
        return None
