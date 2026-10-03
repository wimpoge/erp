from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..models import Activity, today
from ..services import reports as svc
from .deps import Db, can
from .serializers import activity_out

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/dashboard")
def dashboard(db: Db, _: can("reports.read")) -> dict:
    return svc.dashboard(db, today())


@router.get("/sales")
def sales_report(db: Db, _: can("reports.read"), months: int = Query(12, ge=1, le=36)) -> dict:
    since = svc.month_start(today(), months - 1)
    return {
        "monthly": svc.monthly(db, today(), months),
        "by_category": svc.sales_by_category(db, since),
        "top_products": svc.top_products(db, since, 10),
        "top_customers": svc.top_customers(db, since, 10),
    }


@router.get("/inventory")
def inventory_report(db: Db, _: can("reports.read")) -> dict:
    return {"by_warehouse": svc.stock_by_warehouse(db), "total_value": svc.stock_value(db),
            "low_stock": svc.low_stock(db, 50)}


@router.get("/aging")
def aging_report(db: Db, _: can("reports.read"), kind: Literal["customer", "supplier"] = "customer") -> dict:
    return svc.aging(db, kind, today())


@router.get("/activity")
def recent_activity(db: Db, _: can("reports.read"), limit: int = Query(15, ge=1, le=100)) -> list[dict]:
    stmt = select(Activity).options(selectinload(Activity.user)).order_by(Activity.at.desc(), Activity.id.desc())
    return [activity_out(a) for a in db.scalars(stmt.limit(limit))]
