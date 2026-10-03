"""Small JSON shapes reused across modules."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, Customer, Product, Supplier, User, Warehouse


def user_ref(u: User | None) -> dict | None:
    return {"id": u.id, "name": u.full_name} if u else None


def warehouse_ref(w: Warehouse | None) -> dict | None:
    return {"id": w.id, "code": w.code, "name": w.name} if w else None


def product_ref(p: Product) -> dict:
    return {"id": p.id, "sku": p.sku, "name": p.name, "unit": p.unit}


def customer_ref(c: Customer | None) -> dict | None:
    return {"id": c.id, "code": c.code, "name": c.name} if c else None


def supplier_ref(s: Supplier | None) -> dict | None:
    return {"id": s.id, "code": s.code, "name": s.name} if s else None


def activity_out(a: Activity) -> dict:
    return {"id": a.id, "at": a.at, "user": user_ref(a.user), "entity_type": a.entity_type, "entity_id": a.entity_id,
            "action": a.action, "message": a.message}


def timeline(db: Session, entity_type: str, entity_id: int) -> list[dict]:
    stmt = select(Activity).filter_by(entity_type=entity_type, entity_id=entity_id).order_by(Activity.at, Activity.id)
    return [activity_out(a) for a in db.scalars(stmt)]
