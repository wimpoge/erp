from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, PublicIdMixin, TimestampMixin


class Category(Base):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class Product(PublicIdMixin, TimestampMixin, Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"))
    brand: Mapped[str | None] = mapped_column(String(60))
    barcode: Mapped[str | None] = mapped_column(String(20), unique=True)
    unit: Mapped[str] = mapped_column(String(10), default="pcs")
    sale_price: Mapped[int]  # rupiah, excluding tax
    # Moving average cost, updated on every goods receipt; values stock and COGS.
    avg_cost: Mapped[int] = mapped_column(default=0)
    reorder_point: Mapped[int] = mapped_column(default=0)
    active: Mapped[bool] = mapped_column(default=True)

    category: Mapped[Category | None] = relationship()


class Warehouse(PublicIdMixin, Base):
    __tablename__ = "warehouse"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80))
    address: Mapped[str | None] = mapped_column(String(250))
    active: Mapped[bool] = mapped_column(default=True)
