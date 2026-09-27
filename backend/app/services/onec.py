"""Soldurile clienților din 1C: primirea lor de la scriptul de pe calculatorul cu 1C și
vederile pentru admin și director. Contabilii nu primesc niciodată aceste date.

Scriptul se autentifică cu o cheie generată în Setări → 1C (se păstrează doar hash-ul).
Contragenții din 1C se potrivesc cu clienții după IDNO (doar cifrele, 13).
"""

import hashlib
import re
import secrets
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import RecordStatus
from app.models import (
    Client,
    ClientAssignment,
    ClientBalance,
    OneCIntegration,
    OneCSyncRun,
    User,
    UserRole,
)
from app.schemas.onec import (
    ApiKeyOut,
    BalancesIn,
    ClientBalanceOut,
    DebtRowOut,
    DebtsOut,
    OneCStatusOut,
    RunOut,
    SyncResultOut,
    UnmatchedOut,
)
from app.services.audit import AuditService, snapshot
from app.services.errors import ForbiddenError, NotFoundError

KEY_PREFIX = "1c_"
UNMATCHED_LIMIT = 1000  # câți contragenți negăsiți se păstrează (cei cu sold mare primii)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def normalize_idno(value: str) -> str:
    return re.sub(r"\D", "", value)


async def integration_row(session: AsyncSession) -> OneCIntegration:
    row = await session.scalar(select(OneCIntegration).order_by(OneCIntegration.id).limit(1))
    if row is None:
        row = OneCIntegration()
        session.add(row)
        await session.flush()
    return row


async def latest_run(session: AsyncSession) -> OneCSyncRun | None:
    run: OneCSyncRun | None = await session.scalar(
        select(OneCSyncRun).order_by(OneCSyncRun.received_at.desc(), OneCSyncRun.id.desc()).limit(1)
    )
    return run


async def ingest(session: AsyncSession, key: str, data: BalancesIn) -> SyncResultOut | None:
    """Salvează soldurile trimise de script. `None` dacă cheia nu e valabilă."""
    row = await session.scalar(
        select(OneCIntegration).where(OneCIntegration.api_key_hash == hash_key(key))
    )
    if row is None or not secrets.compare_digest(row.api_key_hash or "", hash_key(key)):
        return None

    clients = {
        c.idno: c
        for c in await session.scalars(
            select(Client).where(Client.status == RecordStatus.ACTIVE, Client.deleted_at.is_(None))
        )
    }
    sums: dict[int, list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    unmatched: list[dict[str, object]] = []
    for r in data.rows:
        client = clients.get(normalize_idno(r.idno))
        if client is not None:
            sums[client.id][0] += r.debit
            sums[client.id][1] += r.credit
        elif r.debit or r.credit:
            unmatched.append(
                {
                    "idno": r.idno.strip(),
                    "name": r.name.strip(),
                    "debit": str(r.debit),
                    "credit": str(r.credit),
                }
            )
    unmatched.sort(key=lambda u: Decimal(str(u["debit"])), reverse=True)

    run = OneCSyncRun(
        as_of=data.as_of,
        base_name=data.base,
        script_version=data.script_version,
        rows=len(data.rows),
        matched=len(sums),
        total_debit=sum((d for d, _ in sums.values()), Decimal(0)),
        unmatched=unmatched[:UNMATCHED_LIMIT],
    )
    session.add(run)
    await session.flush()
    session.add_all(
        ClientBalance(run_id=run.id, client_id=cid, debit=d, credit=c)
        for cid, (d, c) in sums.items()
    )
    await session.commit()
    return SyncResultOut(
        run_id=run.id,
        rows=run.rows,
        matched=run.matched,
        unmatched=len(unmatched),
        total_debit=run.total_debit,
    )


class OneCService:
    """Vederile din aplicație. Doar admin și director; cheia o schimbă doar adminul."""

    def __init__(self, session: AsyncSession, actor: User) -> None:
        self.session = session
        self.actor = actor
        self.audit = AuditService(session, actor)
        if actor.role not in (UserRole.ADMIN, UserRole.DIRECTOR):
            raise ForbiddenError("Acces interzis")

    async def status(self) -> OneCStatusOut:
        row = await integration_row(self.session)
        run = await latest_run(self.session)
        await self.session.commit()
        return OneCStatusOut(
            key_configured=row.api_key_hash is not None,
            key_hint=row.api_key_hint,
            last_run=RunOut.model_validate(run) if run else None,
        )

    async def regenerate_key(self) -> ApiKeyOut:
        """Cheie nouă pentru script; cea veche nu mai e acceptată."""
        if self.actor.role is not UserRole.ADMIN:
            raise ForbiddenError("Doar adminul generează cheia")
        key = KEY_PREFIX + secrets.token_urlsafe(32)
        row = await integration_row(self.session)
        before = snapshot(row)
        row.api_key_hash = hash_key(key)
        row.api_key_hint = f"…{key[-4:]}"
        row.updated_by = self.actor.id
        await self.session.flush()
        self.audit.changed(row, before)
        await self.session.commit()
        return ApiKeyOut(key=key, status=await self.status())

    async def debts(self) -> DebtsOut:
        run = await latest_run(self.session)
        if run is None:
            return DebtsOut(run=None, clients=[], unmatched=[])
        rows = (
            await self.session.execute(
                select(ClientBalance, Client)
                .join(Client, Client.id == ClientBalance.client_id)
                .where(ClientBalance.run_id == run.id, ClientBalance.debit > 0)
                .order_by(ClientBalance.debit.desc(), Client.name)
            )
        ).all()
        names: dict[int, list[str]] = defaultdict(list)
        if rows:
            for a, u in await self.session.execute(
                select(ClientAssignment.client_id, User.full_name)
                .join(User, User.id == ClientAssignment.user_id)
                .where(
                    ClientAssignment.client_id.in_([c.id for _, c in rows]),
                    ClientAssignment.unassigned_at.is_(None),
                )
            ):
                names[a].append(u)
        return DebtsOut(
            run=RunOut.model_validate(run),
            clients=[
                DebtRowOut(
                    client_id=c.id,
                    name=c.name,
                    idno=c.idno,
                    debit=b.debit,
                    credit=b.credit,
                    accountants=names[c.id],
                )
                for b, c in rows
            ],
            unmatched=[UnmatchedOut.model_validate(u) for u in run.unmatched],
        )

    async def client_balance(self, client_id: int) -> ClientBalanceOut | None:
        """Soldul clientului la ultima sincronizare (`None`: nicio sincronizare încă;
        clientul lipsă din sincronizare = sold zero)."""
        if await self.session.get(Client, client_id) is None:
            raise NotFoundError("Clientul nu există")
        run = await latest_run(self.session)
        if run is None:
            return None
        balance = await self.session.scalar(
            select(ClientBalance).where(
                ClientBalance.run_id == run.id, ClientBalance.client_id == client_id
            )
        )
        return ClientBalanceOut(
            as_of=run.as_of,
            received_at=run.received_at,
            debit=balance.debit if balance else Decimal(0),
            credit=balance.credit if balance else Decimal(0),
        )
