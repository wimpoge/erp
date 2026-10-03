from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow


class ApiClient(Base):
    """An outside system (a POS, a web shop) allowed to use the integration API."""

    __tablename__ = "api_client"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    client_id: Mapped[str] = mapped_column(String(40), unique=True)
    secret_hash: Mapped[str] = mapped_column(String(64))  # sha256; the secret is shown once
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_used_at: Mapped[datetime | None]


class ApiToken(Base):
    __tablename__ = "api_token"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("api_client.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime]

    client: Mapped[ApiClient] = relationship()
