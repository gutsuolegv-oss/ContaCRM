"""Comenzi de administrare.

    python -m app.cli create-user --email admin@birou.md --full-name "Nume Prenume"
    python -m app.cli create-user --email ana@birou.md --full-name "Ana" --role contabil

Parola se cere interactiv (nu ca argument, ca să nu rămână în istoricul shell-ului).
La primul utilizator, dacă organizația nu există încă, dă și --org-name.
"""

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import get_sessionmaker
from app.models import Organization, User, UserRole
from app.repositories.user import UserRepository

MIN_PASSWORD_LENGTH = 12


def _read_password() -> str:
    password = getpass.getpass("Parolă: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Parola trebuie să aibă cel puțin {MIN_PASSWORD_LENGTH} caractere.")
    if getpass.getpass("Repetă parola: ") != password:
        sys.exit("Parolele nu coincid.")
    return password


async def create_user(
    email: str, full_name: str, role: UserRole, password: str, org_name: str | None
) -> int:
    async with get_sessionmaker()() as session:
        users = UserRepository(session)
        if await users.get_active_by_email(email) is not None:
            sys.exit(f"Există deja un utilizator activ cu emailul {email}.")
        org = await session.scalar(select(Organization).order_by(Organization.id).limit(1))
        if org is None:
            if not org_name:
                sys.exit("Organizația nu există încă: adaugă --org-name.")
            org = Organization(name=org_name)
            session.add(org)
            await session.flush()
        user = User(
            organization_id=org.id,
            email=email.strip().lower(),
            full_name=full_name,
            password_hash=hash_password(password),
            role=role,
        )
        users.add(user)
        await session.commit()
        return user.id


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    cu = sub.add_parser("create-user", help="creează un utilizator")
    cu.add_argument("--email", required=True)
    cu.add_argument("--full-name", required=True)
    cu.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.ADMIN.value)
    cu.add_argument("--org-name", help="numele biroului, dacă organizația nu există încă")
    args = parser.parse_args()

    if args.command == "create-user":
        password = _read_password()
        user_id = asyncio.run(
            create_user(args.email, args.full_name, UserRole(args.role), password, args.org_name)
        )
        print(f"Utilizator creat: id={user_id}, {args.email}, rol {args.role}")


if __name__ == "__main__":
    main()
