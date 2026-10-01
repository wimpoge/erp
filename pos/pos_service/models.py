"""POS schema.

Master-data tables mirror the ERP but own their integer primary keys; `erp_public_id`
links each row to its ERP record. Orders are created here and pushed to the ERP.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    # Naive UTC everywhere: SQLite drops tz info, so aware and naive values never mix.
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class ErpLinkMixin:
    erp_public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    active: Mapped[bool] = mapped_column(default=True)


# ---------------------------------------------------------------- master data (from the ERP)


class Location(ErpLinkMixin, Base):
    __tablename__ = "location"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80))

    registers: Mapped[list["Register"]] = relationship(back_populates="location", order_by="Register.id")


class Register(ErpLinkMixin, Base):
    __tablename__ = "register"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"))
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(80))

    location: Mapped[Location] = relationship(back_populates="registers")


class CustomerGroup(ErpLinkMixin, Base):
    __tablename__ = "customer_group"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(80))
    discount_rate: Mapped[int] = mapped_column(default=0)  # percent


class Customer(ErpLinkMixin, Base):
    __tablename__ = "customer"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(120))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("customer_group.id"))

    group: Mapped[CustomerGroup | None] = relationship()


class Product(ErpLinkMixin, Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    barcode: Mapped[str | None] = mapped_column(String(20))
    brand: Mapped[str] = mapped_column(String(60))
    category: Mapped[str] = mapped_column(String(60))
    price: Mapped[int]  # rupiah


class ProductStock(Base):
    __tablename__ = "product_stock"
    __table_args__ = (
        UniqueConstraint("product_id", "location_id"),
        CheckConstraint("on_hand >= 0", name="ck_product_stock_on_hand"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"))
    on_hand: Mapped[int] = mapped_column(default=0)


# ---------------------------------------------------------------- transactions (made here)


class Order(Base):
    __tablename__ = "order"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    # Sent to the ERP as its idempotency key, so a retried push never creates a duplicate.
    external_id: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: str(uuid.uuid4()))
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"))
    register_id: Mapped[int | None] = mapped_column(ForeignKey("register.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"))
    subtotal: Mapped[int]
    discount: Mapped[int] = mapped_column(default=0)
    total: Mapped[int]
    paid: Mapped[int]
    change: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    # pending -> sent, or failed after too many attempts / a rejection the ERP won't change its mind on
    push_status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    push_attempts: Mapped[int] = mapped_column(default=0)
    next_push_at: Mapped[datetime | None]
    last_push_error: Mapped[str | None] = mapped_column(String(500))
    erp_public_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    erp_number: Mapped[str | None] = mapped_column(String(30))

    location: Mapped[Location] = relationship()
    register: Mapped[Register | None] = relationship()
    customer: Mapped[Customer | None] = relationship()
    lines: Mapped[list["OrderLine"]] = relationship(back_populates="order", order_by="OrderLine.id")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order", order_by="Payment.id")
    push_log: Mapped[list["PushAttempt"]] = relationship(order_by="PushAttempt.id")


class OrderLine(Base):
    __tablename__ = "order_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("order.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    qty: Mapped[int]
    unit_price: Mapped[int]
    line_total: Mapped[int]

    order: Mapped[Order] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()


class Payment(Base):
    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("order.id"))
    method: Mapped[str] = mapped_column(String(10))  # cash | card | qris
    amount: Mapped[int]

    order: Mapped[Order] = relationship(back_populates="payments")


class PushAttempt(Base):
    __tablename__ = "push_attempt"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("order.id"), index=True)
    attempt: Mapped[int]
    ok: Mapped[bool]
    status_code: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


# ---------------------------------------------------------------- integration bookkeeping


class SyncRun(Base):
    __tablename__ = "sync_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(10), default="running")  # running | ok | partial | failed
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class SyncEvent(Base):
    __tablename__ = "sync_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("sync_run.id"), index=True)
    table: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(12))  # insert | update | deactivate | delete | skipped | error
    erp_public_id: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class SyncState(Base):
    __tablename__ = "sync_state"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)  # e.g. "products", "stock:KG01"
    last_synced_at: Mapped[datetime | None]
    last_status: Mapped[str] = mapped_column(String(10))
    rows: Mapped[int] = mapped_column(default=0)
