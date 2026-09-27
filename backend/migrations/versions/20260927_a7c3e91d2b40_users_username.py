"""users.email → users.username (logare cu nume de utilizator, fără domeniu)

Revision ID: a7c3e91d2b40
Revises: cfda4b80984f
Create Date: 2026-09-27 21:00:00.000000+03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e91d2b40"
down_revision: str | None = "cfda4b80984f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users")
    op.alter_column("users", "email", new_column_name="username")
    # „ana.rusu@birou.md” → „ana.rusu”. Dacă două conturi active ajung la același nume,
    # indexul unic de mai jos oprește migrarea (se rezolvă manual înainte).
    op.execute("UPDATE users SET username = lower(split_part(username, '@', 1))")
    op.alter_column(
        "users",
        "username",
        type_=sa.String(length=50),
        existing_type=sa.String(length=255),
        existing_nullable=False,
    )
    op.create_index(
        "uq_users_username_lower",
        "users",
        [sa.literal_column("lower(username)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_username_lower", table_name="users")
    op.alter_column(
        "users",
        "username",
        type_=sa.String(length=255),
        existing_type=sa.String(length=50),
        existing_nullable=False,
    )
    op.alter_column("users", "username", new_column_name="email")
    # Domeniul inițial nu se mai știe; se pune cel folosit până acum.
    op.execute("UPDATE users SET email = email || '@birou.md' WHERE email NOT LIKE '%@%'")
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.literal_column("lower(email)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
