from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow
from .catalog import Product, Warehouse
from .core import User
from .partners import Customer


class SalesOrder(Base):
    __tablename__ = "sales_order"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouse.id"))  # ship from
    # draft -> confirmed -> partially_delivered -> delivered ; draft/confirmed -> cancelled
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    order_date: Mapped[date]
    customer_ref: Mapped[str | None] = mapped_column(String(60))
    note: Mapped[str | None] = mapped_column(String(500))
    tax_rate: Mapped[int] = mapped_column(default=11)
    gross: Mapped[int] = mapped_column(default=0)  # before line discounts
    subtotal: Mapped[int] = mapped_column(default=0)  # after discounts, before tax
    tax: Mapped[int] = mapped_column(default=0)
    total: Mapped[int] = mapped_column(default=0)
    # Orders imported through the integration API carry the caller's id: the idempotency key.
    source: Mapped[str] = mapped_column(String(10), default="manual")  # manual | api
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    points_earned: Mapped[int] = mapped_column(default=0, server_default="0")  # loyalty, on a till sale
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    confirmed_at: Mapped[datetime | None]

    customer: Mapped[Customer] = relationship()
    warehouse: Mapped[Warehouse] = relationship()
    created_by: Mapped[User | None] = relationship()
    lines: Mapped[list["SalesOrderLine"]] = relationship(
        back_populates="order", order_by="SalesOrderLine.id", cascade="all, delete-orphan"
    )
    deliveries: Mapped[list["Delivery"]] = relationship(back_populates="order", order_by="Delivery.id")
    returns: Mapped[list["SalesReturn"]] = relationship(back_populates="order", order_by="SalesReturn.id")


class SalesOrderLine(Base):
    __tablename__ = "sales_order_line"
    __table_args__ = (
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("discount_pct >= 0 AND discount_pct <= 100", name="discount_range"),
        CheckConstraint("qty_delivered <= qty", name="not_over_delivered"),
        CheckConstraint("qty_invoiced <= qty_delivered", name="invoice_only_delivered"),
        CheckConstraint("qty_returned <= qty_delivered", name="return_only_delivered"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_order.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    qty: Mapped[int]
    unit_price: Mapped[int]
    discount_pct: Mapped[int] = mapped_column(default=0)
    line_total: Mapped[int]  # after discount, before tax
    qty_delivered: Mapped[int] = mapped_column(default=0)
    qty_invoiced: Mapped[int] = mapped_column(default=0)
    qty_returned: Mapped[int] = mapped_column(default=0, server_default="0")

    order: Mapped[SalesOrder] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()


class Delivery(Base):
    __tablename__ = "delivery"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_order.id"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouse.id"))
    delivery_date: Mapped[date]
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    order: Mapped[SalesOrder] = relationship(back_populates="deliveries")
    warehouse: Mapped[Warehouse] = relationship()
    created_by: Mapped[User | None] = relationship()
    lines: Mapped[list["DeliveryLine"]] = relationship(order_by="DeliveryLine.id", cascade="all, delete-orphan")


class DeliveryLine(Base):
    __tablename__ = "delivery_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    delivery_id: Mapped[int] = mapped_column(ForeignKey("delivery.id", ondelete="CASCADE"))
    order_line_id: Mapped[int] = mapped_column(ForeignKey("sales_order_line.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    qty: Mapped[int]
    unit_cost: Mapped[int]  # average cost at shipping time = cost of goods sold

    product: Mapped[Product] = relationship()


class SalesReturn(Base):
    """Goods a customer brought back: stock goes in again at the cost it left with, and the money
    goes back out (a credit note settled on the spot). Revenue reports subtract it."""

    __tablename__ = "sales_return"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_order.id"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouse.id"))  # taken back into
    return_date: Mapped[date] = mapped_column(index=True)
    reason: Mapped[str | None] = mapped_column(String(200))
    tax_rate: Mapped[int]
    subtotal: Mapped[int]  # before tax
    tax: Mapped[int]
    total: Mapped[int]  # what was refunded
    # [{"method": "cash", "amount": 111000, "reference": null}]
    refunds: Mapped[list] = mapped_column(JSON, default=list)
    points_reversed: Mapped[int] = mapped_column(default=0)  # loyalty points taken back
    # A till's return carries its own id: a retried request never books it twice.
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    order: Mapped[SalesOrder] = relationship(back_populates="returns")
    warehouse: Mapped[Warehouse] = relationship()
    created_by: Mapped[User | None] = relationship()
    lines: Mapped[list["SalesReturnLine"]] = relationship(order_by="SalesReturnLine.id", cascade="all, delete-orphan")


class SalesReturnLine(Base):
    __tablename__ = "sales_return_line"
    __table_args__ = (CheckConstraint("qty > 0", name="qty_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey("sales_return.id", ondelete="CASCADE"), index=True)
    order_line_id: Mapped[int] = mapped_column(ForeignKey("sales_order_line.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    qty: Mapped[int]
    unit_price: Mapped[int]
    discount_pct: Mapped[int] = mapped_column(default=0)
    line_total: Mapped[int]
    unit_cost: Mapped[int]  # the cost it was shipped at, taken back out of cost of goods sold

    product: Mapped[Product] = relationship()
