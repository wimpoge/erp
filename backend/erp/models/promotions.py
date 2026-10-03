from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, PublicIdMixin, utcnow
from .catalog import Category, Product, Warehouse


class Promotion(PublicIdMixin, Base):
    """A price rule the POS tills apply. Promotions never stack: each till line gets the single
    best discount among its customer's group discount and the promotions that cover it.

    percent   value % off a product, a category, or everything (neither set)
    price     a product sold at `value` rupiah (before tax) instead of its list price
    buy_get   buy `buy_qty` of a product, get `get_qty` more of it free
    voucher   value % off every line once the customer gives `code`, from `min_spend` (before tax)
    """

    __tablename__ = "promotion"
    __table_args__ = (
        CheckConstraint("kind IN ('percent', 'price', 'buy_get', 'voucher')", name="kind_known"),
        CheckConstraint("value >= 0", name="value_not_negative"),
        CheckConstraint("ends_on IS NULL OR starts_on IS NULL OR ends_on >= starts_on", name="dates_in_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("product.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"))
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouse.id"))  # None: every store
    value: Mapped[int] = mapped_column(default=0)  # % for percent and voucher, rupiah for price
    buy_qty: Mapped[int] = mapped_column(default=0)
    get_qty: Mapped[int] = mapped_column(default=0)
    code: Mapped[str | None] = mapped_column(String(30), unique=True)
    min_spend: Mapped[int] = mapped_column(default=0)
    starts_on: Mapped[date | None]
    ends_on: Mapped[date | None]
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    product: Mapped[Product | None] = relationship()
    category: Mapped[Category | None] = relationship()
    warehouse: Mapped[Warehouse | None] = relationship()
