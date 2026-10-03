"""Promotions for the POS tills: special prices, percentages off, buy X get Y, vouchers."""

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models import Promotion, today
from ..services import promotions as svc
from ..services.common import get_or_404
from .deps import Db, can
from .serializers import product_ref, timeline, warehouse_ref

router = APIRouter(prefix="/api/promotions", tags=["promotions"])


def status(p: Promotion, on: date) -> str:
    if not p.active:
        return "inactive"
    if p.starts_on and p.starts_on > on:
        return "scheduled"
    if p.ends_on and p.ends_on < on:
        return "ended"
    return "running"


def promotion_out(p: Promotion, db=None) -> dict:
    out = {
        "id": p.id, "name": p.name, "kind": p.kind, "value": p.value, "buy_qty": p.buy_qty, "get_qty": p.get_qty,
        "code": p.code, "min_spend": p.min_spend, "starts_on": p.starts_on, "ends_on": p.ends_on, "active": p.active,
        "status": status(p, today()),
        "product": product_ref(p.product) if p.product else None,
        "category": {"id": p.category.id, "name": p.category.name} if p.category else None,
        "warehouse": warehouse_ref(p.warehouse) if p.warehouse else None,
    }
    if db is not None:
        out["activity"] = timeline(db, "promotion", p.id)
    return out


class PromotionIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(pattern="^(percent|price|buy_get|voucher)$")
    value: int = Field(0, ge=0)
    product_id: int | None = None
    category_id: int | None = None
    warehouse_id: int | None = None
    buy_qty: int = Field(0, ge=0, le=1000)
    get_qty: int = Field(0, ge=0, le=1000)
    code: str | None = Field(None, max_length=30)
    min_spend: int = Field(0, ge=0)
    starts_on: date | None = None
    ends_on: date | None = None
    active: bool = True


def _load(db, promo_id: int) -> Promotion:
    return get_or_404(db, Promotion, promo_id, "Promotion")


@router.get("")
def list_promotions(db: Db, _: can("sales.read")) -> list[dict]:
    rows = db.scalars(select(Promotion).options(selectinload(Promotion.product), selectinload(Promotion.category),
                                                selectinload(Promotion.warehouse))
                      .order_by(Promotion.active.desc(), Promotion.id.desc()))
    return [promotion_out(p) for p in rows]


@router.get("/{promo_id}")
def get_promotion(promo_id: int, db: Db, _: can("sales.read")) -> dict:
    return promotion_out(_load(db, promo_id), db)


@router.post("", status_code=201)
def create_promotion(body: PromotionIn, db: Db, user: can("sales.write")) -> dict:
    promo = svc.save_promotion(db, user, svc.PromotionIn(**body.model_dump()))
    db.commit()
    return promotion_out(promo, db)


@router.put("/{promo_id}")
def update_promotion(promo_id: int, body: PromotionIn, db: Db, user: can("sales.write")) -> dict:
    promo = svc.save_promotion(db, user, svc.PromotionIn(**body.model_dump()), _load(db, promo_id))
    db.commit()
    return promotion_out(promo, db)
