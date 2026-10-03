from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from ..models import GoodsReceipt, GoodsReceiptLine, Invoice, PurchaseOrder, PurchaseOrderLine, Supplier, today
from ..services import purchasing as svc
from ..services.common import get_or_404
from .deps import Db, Params, can, like, paginate
from .serializers import product_ref, supplier_ref, timeline, user_ref, warehouse_ref

router = APIRouter(prefix="/api/purchase-orders", tags=["purchasing"])


class LineIn(BaseModel):
    product_id: int
    qty: int = Field(gt=0, le=100_000)
    unit_cost: int = Field(ge=0)


class OrderIn(BaseModel):
    supplier_id: int
    warehouse_id: int
    order_date: date | None = None
    expected_date: date | None = None
    supplier_ref: str | None = Field(None, max_length=60)
    note: str | None = Field(None, max_length=500)
    lines: list[LineIn] = Field(min_length=1, max_length=200)

    def to_service(self) -> svc.PurchaseOrderIn:
        return svc.PurchaseOrderIn(
            supplier_id=self.supplier_id, warehouse_id=self.warehouse_id, order_date=self.order_date or today(),
            expected_date=self.expected_date, supplier_ref=self.supplier_ref, note=self.note,
            lines=[svc.PurchaseLineIn(li.product_id, li.qty, li.unit_cost) for li in self.lines])


class ReceiveIn(BaseModel):
    receipt_date: date | None = None
    lines: dict[int, int] = Field(description="order line id -> quantity received now")


class BillIn(BaseModel):
    bill_date: date | None = None
    supplier_ref: str | None = Field(None, max_length=60)


def order_out(o: PurchaseOrder, detail: bool = False, db=None) -> dict:
    out = {
        "id": o.id, "number": o.number, "status": o.status, "billing_status": svc.billing_status(o),
        "supplier": supplier_ref(o.supplier), "warehouse": warehouse_ref(o.warehouse),
        "order_date": o.order_date, "expected_date": o.expected_date, "supplier_ref": o.supplier_ref,
        "subtotal": o.subtotal, "tax_rate": o.tax_rate, "tax": o.tax, "total": o.total,
        "received_pct": round(100 * sum(li.qty_received for li in o.lines) / max(1, sum(li.qty for li in o.lines))),
    }
    if detail:
        out.update({
            "note": o.note, "created_by": user_ref(o.created_by), "created_at": o.created_at,
            "lines": [{"id": li.id, "product": product_ref(li.product), "qty": li.qty, "unit_cost": li.unit_cost,
                       "line_total": li.line_total, "qty_received": li.qty_received, "qty_billed": li.qty_billed}
                      for li in o.lines],
            "receipts": [{"id": r.id, "number": r.number, "receipt_date": r.receipt_date,
                          "units": sum(li.qty for li in r.lines), "created_by": user_ref(r.created_by),
                          "lines": [{"product": product_ref(li.product), "qty": li.qty} for li in r.lines]}
                         for r in o.receipts],
            "bills": [{"id": b.id, "number": b.number, "issue_date": b.issue_date, "due_date": b.due_date,
                       "status": b.status, "total": b.total, "balance": b.balance}
                      for b in db.scalars(select(Invoice).filter_by(purchase_order_id=o.id).order_by(Invoice.id))],
            "activity": timeline(db, "purchase_order", o.id),
        })
    return out


def _load(db, order_id: int) -> PurchaseOrder:
    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id).options(
        selectinload(PurchaseOrder.lines).selectinload(PurchaseOrderLine.product),
        selectinload(PurchaseOrder.receipts).selectinload(GoodsReceipt.lines).selectinload(GoodsReceiptLine.product)))
    if order is None:
        get_or_404(db, PurchaseOrder, order_id, "Purchase order")
    return order


@router.get("")
def list_orders(db: Db, _: can("purchasing.read"), params: Params, status: str | None = None,
                supplier_id: int | None = None, date_from: date | None = None, date_to: date | None = None) -> dict:
    stmt = select(PurchaseOrder).join(PurchaseOrder.supplier).options(
        selectinload(PurchaseOrder.supplier), selectinload(PurchaseOrder.warehouse), selectinload(PurchaseOrder.lines))
    if status == "open":
        stmt = stmt.where(PurchaseOrder.status.in_(("confirmed", "partially_received")))
    elif status:
        stmt = stmt.where(PurchaseOrder.status == status)
    if supplier_id:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    if date_from:
        stmt = stmt.where(PurchaseOrder.order_date >= date_from)
    if date_to:
        stmt = stmt.where(PurchaseOrder.order_date <= date_to)
    if params.q:
        stmt = stmt.where(or_(PurchaseOrder.number.ilike(like(params.q)), Supplier.name.ilike(like(params.q)),
                              PurchaseOrder.supplier_ref.ilike(like(params.q))))
    return paginate(db, stmt, params, order_out,
                    sortable={"number": PurchaseOrder.number, "date": PurchaseOrder.order_date,
                              "supplier": Supplier.name, "total": PurchaseOrder.total},
                    default_sort=[PurchaseOrder.order_date.desc(), PurchaseOrder.id.desc()])


@router.get("/{order_id}")
def get_order(order_id: int, db: Db, _: can("purchasing.read")) -> dict:
    return order_out(_load(db, order_id), True, db)


@router.post("", status_code=201)
def create_order(body: OrderIn, db: Db, user: can("purchasing.write")) -> dict:
    order = svc.save_order(db, user, body.to_service())
    db.commit()
    return order_out(_load(db, order.id), True, db)


@router.put("/{order_id}")
def update_order(order_id: int, body: OrderIn, db: Db, user: can("purchasing.write")) -> dict:
    svc.save_order(db, user, body.to_service(), _load(db, order_id))
    db.commit()
    return order_out(_load(db, order_id), True, db)


@router.post("/{order_id}/confirm")
def confirm_order(order_id: int, db: Db, user: can("purchasing.write")) -> dict:
    svc.confirm(db, user, _load(db, order_id))
    db.commit()
    return order_out(_load(db, order_id), True, db)


@router.post("/{order_id}/cancel")
def cancel_order(order_id: int, db: Db, user: can("purchasing.write")) -> dict:
    svc.cancel(db, user, _load(db, order_id))
    db.commit()
    return order_out(_load(db, order_id), True, db)


@router.post("/{order_id}/receive")
def receive_order(order_id: int, body: ReceiveIn, db: Db, user: can("purchasing.receive")) -> dict:
    svc.receive(db, user, _load(db, order_id), body.lines, body.receipt_date or today())
    db.commit()
    return order_out(_load(db, order_id), True, db)


@router.post("/{order_id}/bill")
def bill_order(order_id: int, body: BillIn, db: Db, user: can("finance.write")) -> dict:
    bill = svc.create_bill(db, user, _load(db, order_id), body.bill_date or today(), body.supplier_ref)
    db.commit()
    return {"id": bill.id, "number": bill.number}
