from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow
from .catalog import Product
from .core import User
from .partners import Customer, Supplier
from .purchasing import PurchaseOrder
from .sales import SalesOrder


class Invoice(Base):
    """Customer invoice (accounts receivable) or supplier bill (accounts payable)."""

    __tablename__ = "invoice"
    __table_args__ = (
        CheckConstraint("amount_paid >= 0 AND amount_paid <= total", name="paid_within_total"),
        CheckConstraint(
            "(kind = 'customer' AND customer_id IS NOT NULL) OR (kind = 'supplier' AND supplier_id IS NOT NULL)",
            name="partner_matches_kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    kind: Mapped[str] = mapped_column(String(10), index=True)  # customer | supplier
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customer.id"), index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), index=True)
    sales_order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_order.id"))
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_order.id"))
    # open -> paid ; open (nothing paid) -> cancelled. "Partially paid" and "overdue" are derived.
    status: Mapped[str] = mapped_column(String(12), default="open", index=True)
    issue_date: Mapped[date]
    due_date: Mapped[date] = mapped_column(index=True)
    partner_ref: Mapped[str | None] = mapped_column(String(60))  # e.g. the supplier's own bill number
    tax_rate: Mapped[int] = mapped_column(default=11)
    subtotal: Mapped[int] = mapped_column(default=0)
    tax: Mapped[int] = mapped_column(default=0)
    total: Mapped[int] = mapped_column(default=0)
    amount_paid: Mapped[int] = mapped_column(default=0)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    customer: Mapped[Customer | None] = relationship()
    supplier: Mapped[Supplier | None] = relationship()
    sales_order: Mapped[SalesOrder | None] = relationship()
    purchase_order: Mapped[PurchaseOrder | None] = relationship()
    created_by: Mapped[User | None] = relationship()
    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", order_by="InvoiceLine.id", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice", order_by="Payment.id")

    @property
    def balance(self) -> int:
        return self.total - self.amount_paid


class InvoiceLine(Base):
    __tablename__ = "invoice_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    qty: Mapped[int]
    unit_price: Mapped[int]
    discount_pct: Mapped[int] = mapped_column(default=0)
    line_total: Mapped[int]
    sales_order_line_id: Mapped[int | None] = mapped_column(ForeignKey("sales_order_line.id"))
    purchase_order_line_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_order_line.id"))

    invoice: Mapped[Invoice] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()


class Payment(Base):
    __tablename__ = "payment"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id"), index=True)
    payment_date: Mapped[date]
    amount: Mapped[int]
    method: Mapped[str] = mapped_column(String(20))  # bank_transfer | cash | card | qris
    reference: Mapped[str | None] = mapped_column(String(80))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    invoice: Mapped[Invoice] = relationship(back_populates="payments")
    created_by: Mapped[User | None] = relationship()
