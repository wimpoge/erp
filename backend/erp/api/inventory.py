"""Stock levels, the movement ledger, transfers and stock counts."""

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from ..models import Adjustment, AdjustmentLine, Product, StockLevel, StockMove, Transfer, TransferLine, today
from ..services import inventory as svc
from ..services.common import get_or_404
from .catalog import move_out
from .deps import Db, Params, can, like, paginate
from .serializers import product_ref, timeline, user_ref, warehouse_ref

router = APIRouter(prefix="/api", tags=["inventory"])


@router.get("/stock")
def list_stock(db: Db, _: can("catalog.read"), params: Params, warehouse_id: int | None = None,
               only_low: bool = False) -> dict:
    """One row per product and warehouse that has (or had) stock."""
    stmt = (select(StockLevel).join(StockLevel.product)
            .options(selectinload(StockLevel.product), selectinload(StockLevel.warehouse)))
    if warehouse_id:
        stmt = stmt.where(StockLevel.warehouse_id == warehouse_id)
    if params.q:
        stmt = stmt.where(or_(Product.name.ilike(like(params.q)), Product.sku.ilike(like(params.q))))
    if only_low:
        stmt = stmt.where(Product.reorder_point > 0, StockLevel.on_hand <= Product.reorder_point)
    page = paginate(db, stmt, params, lambda s: s,
                    sortable={"product": Product.name, "on_hand": StockLevel.on_hand,
                              "value": StockLevel.on_hand * Product.avg_cost},
                    default_sort=[Product.name, StockLevel.warehouse_id])
    reserved = svc.reserved_qty(db, [s.product_id for s in page["items"]])
    page["items"] = [{
        "id": s.id, "product": product_ref(s.product), "warehouse": warehouse_ref(s.warehouse),
        "on_hand": s.on_hand, "reserved": reserved.get((s.product_id, s.warehouse_id), 0),
        "available": s.on_hand - reserved.get((s.product_id, s.warehouse_id), 0),
        "unit_cost": s.product.avg_cost, "value": s.on_hand * s.product.avg_cost,
        "reorder_point": s.product.reorder_point,
    } for s in page["items"]]
    return page


@router.get("/stock-moves")
def list_moves(db: Db, _: can("catalog.read"), params: Params, product_id: int | None = None,
               warehouse_id: int | None = None, kind: str | None = None, date_from: date | None = None,
               date_to: date | None = None) -> dict:
    stmt = (select(StockMove).join(StockMove.product)
            .options(selectinload(StockMove.product), selectinload(StockMove.warehouse), selectinload(StockMove.user)))
    if product_id:
        stmt = stmt.where(StockMove.product_id == product_id)
    if warehouse_id:
        stmt = stmt.where(StockMove.warehouse_id == warehouse_id)
    if kind:
        stmt = stmt.where(StockMove.kind == kind)
    if date_from:
        stmt = stmt.where(StockMove.moved_at >= date_from)
    if date_to:
        stmt = stmt.where(StockMove.moved_at < date.fromordinal(date_to.toordinal() + 1))
    if params.q:
        stmt = stmt.where(or_(Product.name.ilike(like(params.q)), Product.sku.ilike(like(params.q)),
                              StockMove.ref_number.ilike(like(params.q))))
    return paginate(db, stmt, params, lambda m: {**move_out(m), "product": product_ref(m.product)},
                    sortable={"at": StockMove.moved_at, "qty": StockMove.qty},
                    default_sort=[StockMove.moved_at.desc(), StockMove.id.desc()])


# ---------------------------------------------------------------- transfers


class QtyLineIn(BaseModel):
    product_id: int
    qty: int = Field(gt=0, le=100_000)


class TransferIn(BaseModel):
    from_warehouse_id: int
    to_warehouse_id: int
    transfer_date: date | None = None
    note: str | None = Field(None, max_length=500)
    lines: list[QtyLineIn] = Field(min_length=1, max_length=200)


def transfer_out(t: Transfer, detail: bool = False, db=None) -> dict:
    out = {"id": t.id, "number": t.number, "status": t.status, "transfer_date": t.transfer_date,
           "from_warehouse": warehouse_ref(t.from_warehouse), "to_warehouse": warehouse_ref(t.to_warehouse),
           "note": t.note, "units": sum(li.qty for li in t.lines), "created_by": user_ref(t.created_by)}
    if detail:
        out["lines"] = [{"id": li.id, "product": product_ref(li.product), "qty": li.qty} for li in t.lines]
        out["activity"] = timeline(db, "transfer", t.id)
    return out


_transfer_load = (selectinload(Transfer.from_warehouse), selectinload(Transfer.to_warehouse),
                  selectinload(Transfer.created_by), selectinload(Transfer.lines).selectinload(TransferLine.product))


@router.get("/transfers")
def list_transfers(db: Db, _: can("catalog.read"), params: Params, status: str | None = None) -> dict:
    stmt = select(Transfer).options(*_transfer_load)
    if status:
        stmt = stmt.where(Transfer.status == status)
    if params.q:
        stmt = stmt.where(Transfer.number.ilike(like(params.q)))
    return paginate(db, stmt, params, transfer_out, sortable={"number": Transfer.number, "date": Transfer.transfer_date},
                    default_sort=[Transfer.id.desc()])


@router.get("/transfers/{transfer_id}")
def get_transfer(transfer_id: int, db: Db, _: can("catalog.read")) -> dict:
    return transfer_out(get_or_404(db, Transfer, transfer_id, "Transfer"), True, db)


@router.post("/transfers", status_code=201)
def create_transfer(body: TransferIn, db: Db, user: can("inventory.write")) -> dict:
    t = svc.create_transfer(db, user, body.from_warehouse_id, body.to_warehouse_id, body.transfer_date or today(),
                            [svc.QtyLine(li.product_id, li.qty) for li in body.lines], body.note)
    db.commit()
    return transfer_out(t, True, db)


@router.post("/transfers/{transfer_id}/validate")
def validate_transfer(transfer_id: int, db: Db, user: can("inventory.write")) -> dict:
    t = svc.validate_transfer(db, user, get_or_404(db, Transfer, transfer_id, "Transfer"))
    db.commit()
    return transfer_out(t, True, db)


@router.post("/transfers/{transfer_id}/cancel")
def cancel_transfer(transfer_id: int, db: Db, user: can("inventory.write")) -> dict:
    t = svc.cancel_transfer(db, user, get_or_404(db, Transfer, transfer_id, "Transfer"))
    db.commit()
    return transfer_out(t, True, db)


# ---------------------------------------------------------------- stock counts


class CountLineIn(BaseModel):
    product_id: int
    counted_qty: int = Field(ge=0, le=1_000_000)


class AdjustmentIn(BaseModel):
    warehouse_id: int
    adjustment_date: date | None = None
    reason: str = Field(min_length=1, max_length=200)
    lines: list[CountLineIn] = Field(min_length=1, max_length=500)


def adjustment_out(a: Adjustment, detail: bool = False, db=None) -> dict:
    out = {"id": a.id, "number": a.number, "status": a.status, "adjustment_date": a.adjustment_date,
           "warehouse": warehouse_ref(a.warehouse), "reason": a.reason, "products": len(a.lines),
           "created_by": user_ref(a.created_by)}
    if detail:
        current = {}
        if a.status == "draft":
            current = {pid: q for pid, q in db.execute(
                select(StockLevel.product_id, StockLevel.on_hand).filter_by(warehouse_id=a.warehouse_id))}
        out["lines"] = []
        for li in a.lines:
            system = li.system_qty if li.system_qty is not None else current.get(li.product_id, 0)
            out["lines"].append({"id": li.id, "product": product_ref(li.product), "counted_qty": li.counted_qty,
                                 "system_qty": system, "difference": li.counted_qty - system,
                                 "value": (li.counted_qty - system) * li.product.avg_cost})
        out["activity"] = timeline(db, "adjustment", a.id)
    return out


_adjustment_load = (selectinload(Adjustment.warehouse), selectinload(Adjustment.created_by),
                    selectinload(Adjustment.lines).selectinload(AdjustmentLine.product))


@router.get("/adjustments")
def list_adjustments(db: Db, _: can("catalog.read"), params: Params, status: str | None = None) -> dict:
    stmt = select(Adjustment).options(*_adjustment_load)
    if status:
        stmt = stmt.where(Adjustment.status == status)
    if params.q:
        stmt = stmt.where(or_(Adjustment.number.ilike(like(params.q)), Adjustment.reason.ilike(like(params.q))))
    return paginate(db, stmt, params, adjustment_out, sortable={"number": Adjustment.number,
                                                                "date": Adjustment.adjustment_date},
                    default_sort=[Adjustment.id.desc()])


@router.get("/adjustments/{adjustment_id}")
def get_adjustment(adjustment_id: int, db: Db, _: can("catalog.read")) -> dict:
    return adjustment_out(get_or_404(db, Adjustment, adjustment_id, "Adjustment"), True, db)


@router.post("/adjustments", status_code=201)
def create_adjustment(body: AdjustmentIn, db: Db, user: can("inventory.write")) -> dict:
    a = svc.create_adjustment(db, user, body.warehouse_id, body.adjustment_date or today(), body.reason,
                              [svc.CountLine(li.product_id, li.counted_qty) for li in body.lines])
    db.commit()
    return adjustment_out(a, True, db)


@router.post("/adjustments/{adjustment_id}/validate")
def validate_adjustment(adjustment_id: int, db: Db, user: can("inventory.write")) -> dict:
    a = svc.validate_adjustment(db, user, get_or_404(db, Adjustment, adjustment_id, "Adjustment"))
    db.commit()
    return adjustment_out(a, True, db)


@router.post("/adjustments/{adjustment_id}/cancel")
def cancel_adjustment(adjustment_id: int, db: Db, user: can("inventory.write")) -> dict:
    a = svc.cancel_adjustment(db, user, get_or_404(db, Adjustment, adjustment_id, "Adjustment"))
    db.commit()
    return adjustment_out(a, True, db)


@router.get("/products/{product_id}/moves")
def product_moves(product_id: int, db: Db, u: can("catalog.read"), params: Params) -> dict:
    get_or_404(db, Product, product_id, "Product")
    return list_moves(db, u, params, product_id=product_id)
