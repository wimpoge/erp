from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow


class User(Base):
    __tablename__ = "user_account"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)  # what people log in with
    email: Mapped[str] = mapped_column(String(120), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))  # see erp.permissions.ROLES
    active: Mapped[bool] = mapped_column(default=True)
    failed_logins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None]
    last_login_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class AuthSession(Base):
    """Server-side login session. Only a hash of the cookie value is stored."""

    __tablename__ = "auth_session"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_account.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    user: Mapped[User] = relationship()


class Activity(Base):
    """Audit trail: who did what to which record, shown as a timeline on every document."""

    __tablename__ = "activity"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int]
    action: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(String(500))

    user: Mapped[User | None] = relationship()


class NumberSequence(Base):
    """Gapless document numbers per prefix and year, e.g. SO-2026-00042."""

    __tablename__ = "number_sequence"

    key: Mapped[str] = mapped_column(String(20), primary_key=True)  # "SO-2026"
    next_value: Mapped[int] = mapped_column(default=1)


class Setting(Base):
    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
