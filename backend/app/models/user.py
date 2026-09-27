import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin, str_enum


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    DIRECTOR = "director"
    CONTABIL = "contabil"


class User(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Emailul e unic doar printre utilizatorii neșterși; comparația ignoră majusculele.
        Index(
            "uq_users_email_lower",
            func.lower(text("email")),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    organization_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    email: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole, "role"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Parola a fost setată de admin (cont nou / resetare): până o schimbă, utilizatorul poate
    # doar să-și vadă profilul și să-și schimbe parola.
    must_change_password: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Versiunea sesiunilor, copiată în fiecare access token. Crește la schimbarea sau
    # resetarea parolei și la arhivare: tokenurile cu versiune veche sunt refuzate.
    session_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class RefreshToken(IdMixin, Base):
    """Se salvează doar hash-ul tokenului; tokenul în clar îl are doar clientul."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # SHA-256, hex
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
