from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow
from .catalog import Product, Warehouse
from .core import User
from .partners import Supplier


class PurchaseOrder(Base):
    __tablename__ = "purchase_order"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouse.id"))  # deliver to
    # draft -> confirmed -> partially_received -> received ; draft/confirmed -> cancelled
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    order_date: Mapped[date]
    expected_date: Mapped[date | None]
    supplier_ref: Mapped[str | None] = mapped_column(String(60))
    note: Mapped[str | None] = mapped_column(String(500))
    tax_rate: Mapped[int] = mapped_column(default=11)  # percent
    subtotal: Mapped[int] = mapped_column(default=0)
    tax: Mapped[int] = mapped_column(default=0)
    total: Mapped[int] = mapped_column(default=0)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    confirmed_at: Mapped[datetime | None]

    supplier: Mapped[Supplier] = relationship()
    warehouse: Mapped[Warehouse] = relationship()
    created_by: Mapped[User | None] = relationship()
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        back_populates="order", order_by="PurchaseOrderLine.id", cascade="all, delete-orphan"
    )
    receipts: Mapped[list["GoodsReceipt"]] = relationship(back_populates="order", order_by="GoodsReceipt.id")


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_line"
    __table_args__ = (
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("qty_received <= qty", name="not_over_received"),
        CheckConstraint("qty_billed <= qty_received", name="bill_only_received"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("purchase_order.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    qty: Mapped[int]
    unit_cost: Mapped[int]
    line_total: Mapped[int]
    qty_received: Mapped[int] = mapped_column(default=0)
    qty_billed: Mapped[int] = mapped_column(default=0)

    order: Mapped[PurchaseOrder] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()


class GoodsReceipt(Base):
    __tablename__ = "goods_receipt"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("purchase_order.id"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouse.id"))
    receipt_date: Mapped[date]
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    order: Mapped[PurchaseOrder] = relationship(back_populates="receipts")
    warehouse: Mapped[Warehouse] = relationship()
    created_by: Mapped[User | None] = relationship()
    lines: Mapped[list["GoodsReceiptLine"]] = relationship(order_by="GoodsReceiptLine.id", cascade="all, delete-orphan")


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("goods_receipt.id", ondelete="CASCADE"))
    order_line_id: Mapped[int] = mapped_column(ForeignKey("purchase_order_line.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    qty: Mapped[int]
    unit_cost: Mapped[int]

    product: Mapped[Product] = relationship()
