from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, PublicIdMixin, TimestampMixin


class CustomerGroup(Base):
    __tablename__ = "customer_group"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    discount_pct: Mapped[int] = mapped_column(default=0)  # default line discount on sales orders


class Customer(PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "customer"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    email: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(String(250))
    city: Mapped[str | None] = mapped_column(String(80))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("customer_group.id"))
    # 0 = no limit. Confirming an order that would push open invoices + orders past it is refused.
    credit_limit: Mapped[int] = mapped_column(default=0)
    payment_terms_days: Mapped[int] = mapped_column(default=30)
    active: Mapped[bool] = mapped_column(default=True)

    group: Mapped[CustomerGroup | None] = relationship()


class Supplier(PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "supplier"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    email: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(String(250))
    city: Mapped[str | None] = mapped_column(String(80))
    payment_terms_days: Mapped[int] = mapped_column(default=30)
    active: Mapped[bool] = mapped_column(default=True)
