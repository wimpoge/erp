import uuid
from datetime import UTC, date, datetime

from sqlalchemy import MetaData, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    # Naive UTC everywhere: SQLite drops tz info, so aware and naive values never mix.
    return datetime.now(UTC).replace(tzinfo=None)


def today() -> date:
    return utcnow().date()


class Base(DeclarativeBase):
    # Stable constraint names, so Alembic migrations behave the same on SQLite and Postgres.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class PublicIdMixin:
    """Integer keys stay internal; the integration API only exposes this UUID."""

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=uuid.uuid4)
