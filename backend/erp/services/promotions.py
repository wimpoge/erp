"""Promotions the POS tills apply. Kept here so every store prices the same way; the tills
pull them with the rest of the master data."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import Category, Product, Promotion, User, Warehouse
from .common import DomainError, log

KINDS = ("percent", "price", "buy_get", "voucher")


@dataclass
class PromotionIn:
    name: str
    kind: str
    value: int = 0
    product_id: int | None = None
    category_id: int | None = None
    warehouse_id: int | None = None
    buy_qty: int = 0
    get_qty: int = 0
    code: str | None = None
    min_spend: int = 0
    starts_on: date | None = None
    ends_on: date | None = None
    active: bool = True


def save_promotion(db: Session, user: User, data: PromotionIn, promo: Promotion | None = None) -> Promotion:
    name = data.name.strip()
    if not name:
        raise DomainError(422, "Give the promotion a name.")
    if data.kind not in KINDS:
        raise DomainError(422, f"Kind must be one of: {', '.join(KINDS)}.")
    if data.starts_on and data.ends_on and data.ends_on < data.starts_on:
        raise DomainError(422, "The promotion must end on or after the day it starts.")
    product = db.get(Product, data.product_id) if data.product_id else None
    if data.product_id and product is None:
        raise DomainError(422, "Unknown product.")
    if data.category_id and db.get(Category, data.category_id) is None:
        raise DomainError(422, "Unknown category.")
    if data.warehouse_id and db.get(Warehouse, data.warehouse_id) is None:
        raise DomainError(422, "Unknown store.")

    product_id, category_id, code = data.product_id, data.category_id, None
    value, buy_qty, get_qty, min_spend = data.value, 0, 0, 0
    if data.kind == "percent":
        if not 1 <= value <= 100:
            raise DomainError(422, "The discount must be between 1 and 100%.")
        if product_id and category_id:
            raise DomainError(422, "Pick a product or a category, not both (neither: everything).")
    elif data.kind == "price":
        if product is None:
            raise DomainError(422, "A special price needs a product.")
        if not 0 <= value < product.sale_price:
            raise DomainError(422, f"The special price must be below the list price of {product.sale_price:,}.")
        category_id = None
    elif data.kind == "buy_get":
        if product is None:
            raise DomainError(422, "Buy X get Y needs a product.")
        if data.buy_qty < 1 or data.get_qty < 1:
            raise DomainError(422, "Buy at least 1 and get at least 1 free.")
        buy_qty, get_qty, value, category_id = data.buy_qty, data.get_qty, 0, None
    else:  # voucher
        if not 1 <= value <= 100:
            raise DomainError(422, "The voucher discount must be between 1 and 100%.")
        code = (data.code or "").strip().upper()
        if not code:
            raise DomainError(422, "A voucher needs a code for the customer to give.")
        clash = db.scalar(select(Promotion).where(func.upper(Promotion.code) == code,
                                                  Promotion.id != (promo.id if promo else -1)))
        if clash is not None:
            raise DomainError(409, f"Voucher code {code} is already used by {clash.name}.")
        product_id, category_id, min_spend = None, None, max(data.min_spend, 0)

    created = promo is None
    if created:
        promo = Promotion()
        db.add(promo)
    promo.name, promo.kind, promo.value = name, data.kind, value
    promo.product_id, promo.category_id, promo.warehouse_id = product_id, category_id, data.warehouse_id
    promo.buy_qty, promo.get_qty, promo.code, promo.min_spend = buy_qty, get_qty, code, min_spend
    promo.starts_on, promo.ends_on, promo.active = data.starts_on, data.ends_on, data.active
    db.flush()
    log(db, user, "promotion", promo.id, "created" if created else "updated",
        f"Promotion {promo.name} {'created' if created else 'updated'}")
    return promo


def current_promotions(db: Session, on: date):
    """Active promotions that have not ended: running now or starting later (a till syncs ahead)."""
    return select(Promotion).where(Promotion.active, or_(Promotion.ends_on.is_(None), Promotion.ends_on >= on))
