"""Mock ERP schema: the master data the POS mirrors, plus the sales orders it pushes."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    # Naive UTC everywhere: SQLite drops tz info, so aware and naive values never mix.
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class PublicIdMixin:
    """Integer ids stay internal; the API only ever exposes this UUID."""

    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=uuid.uuid4)


class Store(PublicIdMixin, Base):
    __tablename__ = "store"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    registers: Mapped[list["Register"]] = relationship(back_populates="store", order_by="Register.id")


class Register(PublicIdMixin, Base):
    __tablename__ = "register"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("store.id"))
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(default=True)

    store: Mapped[Store] = relationship(back_populates="registers")


class CustomerGroup(PublicIdMixin, Base):
    __tablename__ = "customer_group"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    discount_rate: Mapped[int] = mapped_column(default=0)  # percent
    active: Mapped[bool] = mapped_column(default=True)


class Customer(PublicIdMixin, Base):
    __tablename__ = "customer"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(120))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("customer_group.id"))
    active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    group: Mapped[CustomerGroup | None] = relationship()


class Product(PublicIdMixin, Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    barcode: Mapped[str | None] = mapped_column(String(20), unique=True)
    brand: Mapped[str] = mapped_column(String(60))
    category: Mapped[str] = mapped_column(String(60))
    price: Mapped[int]  # rupiah, no decimals
    active: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Stock(Base):
    __tablename__ = "stock"
    __table_args__ = (UniqueConstraint("product_id", "store_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    store_id: Mapped[int] = mapped_column(ForeignKey("store.id"))
    on_hand: Mapped[int] = mapped_column(default=0)

    product: Mapped[Product] = relationship()


class SalesOrder(PublicIdMixin, Base):
    __tablename__ = "sales_order"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str | None] = mapped_column(String(30), unique=True)
    # The POS's own order id: the idempotency key for pushes.
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("store.id"))
    register_id: Mapped[int | None] = mapped_column(ForeignKey("register.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"))
    subtotal: Mapped[int]
    discount: Mapped[int] = mapped_column(default=0)
    total: Mapped[int]
    ordered_at: Mapped[datetime]
    received_at: Mapped[datetime] = mapped_column(default=utcnow)

    store: Mapped[Store] = relationship()
    register: Mapped[Register | None] = relationship()
    customer: Mapped[Customer | None] = relationship()
    lines: Mapped[list["SalesOrderLine"]] = relationship(back_populates="order", order_by="SalesOrderLine.id")


class SalesOrderLine(Base):
    __tablename__ = "sales_order_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_order.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    qty: Mapped[int]
    unit_price: Mapped[int]
    line_total: Mapped[int]

    order: Mapped[SalesOrder] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()


class ApiClient(Base):
    __tablename__ = "api_client"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String(60), unique=True)
    secret_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex
    app_code: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(default=True)


class ApiToken(Base):
    __tablename__ = "api_token"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("api_client.id"))
    expires_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    client: Mapped[ApiClient] = relationship()
