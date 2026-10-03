from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow
from .catalog import Product, Warehouse
from .core import User


class StockLevel(Base):
    """Current quantity per product per warehouse. Changed only through StockMove postings."""

    __tablename__ = "stock_level"
    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_id"),
        CheckConstraint("on_hand >= 0", name="on_hand_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouse.id"))
    on_hand: Mapped[int] = mapped_column(default=0)

    product: Mapped[Product] = relationship()
    warehouse: Mapped[Warehouse] = relationship()


class StockMove(Base):
    """The inventory ledger: every change to stock, signed, with its cost and source document."""

    __tablename__ = "stock_move"

    id: Mapped[int] = mapped_column(primary_key=True)
    moved_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), index=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouse.id"), index=True)
    qty: Mapped[int]  # + in, - out
    unit_cost: Mapped[int]
    # opening | receipt | delivery | transfer_in | transfer_out | adjustment
    kind: Mapped[str] = mapped_column(String(20))
    ref_type: Mapped[str | None] = mapped_column(String(30))
    ref_id: Mapped[int | None]
    ref_number: Mapped[str | None] = mapped_column(String(30))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))

    product: Mapped[Product] = relationship()
    warehouse: Mapped[Warehouse] = relationship()
    user: Mapped[User | None] = relationship()


class Transfer(Base):
    __tablename__ = "transfer"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    from_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouse.id"))
    to_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouse.id"))
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft | done | cancelled
    transfer_date: Mapped[date]
    note: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    from_warehouse: Mapped[Warehouse] = relationship(foreign_keys=[from_warehouse_id])
    to_warehouse: Mapped[Warehouse] = relationship(foreign_keys=[to_warehouse_id])
    created_by: Mapped[User | None] = relationship()
    lines: Mapped[list["TransferLine"]] = relationship(
        back_populates="transfer", order_by="TransferLine.id", cascade="all, delete-orphan"
    )


class TransferLine(Base):
    __tablename__ = "transfer_line"
    __table_args__ = (CheckConstraint("qty > 0", name="qty_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("transfer.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    qty: Mapped[int]

    transfer: Mapped[Transfer] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()


class Adjustment(Base):
    """Stock count: counted quantities replace the system quantity when validated."""

    __tablename__ = "adjustment"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouse.id"))
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft | done | cancelled
    adjustment_date: Mapped[date]
    reason: Mapped[str] = mapped_column(String(200))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    warehouse: Mapped[Warehouse] = relationship()
    created_by: Mapped[User | None] = relationship()
    lines: Mapped[list["AdjustmentLine"]] = relationship(
        back_populates="adjustment", order_by="AdjustmentLine.id", cascade="all, delete-orphan"
    )


class AdjustmentLine(Base):
    __tablename__ = "adjustment_line"
    __table_args__ = (CheckConstraint("counted_qty >= 0", name="counted_not_negative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    adjustment_id: Mapped[int] = mapped_column(ForeignKey("adjustment.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"))
    counted_qty: Mapped[int]
    system_qty: Mapped[int | None]  # filled in when validated

    adjustment: Mapped[Adjustment] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()
