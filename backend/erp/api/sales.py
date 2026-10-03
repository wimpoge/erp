from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from ..models import Customer, Delivery, DeliveryLine, Invoice, SalesOrder, SalesOrderLine, today
from ..services import sales as svc
from ..services.common import get_or_404
from ..services.inventory import availability
from .deps import Db, Params, can, like, paginate
from .serializers import customer_ref, product_ref, timeline, user_ref, warehouse_ref

router = APIRouter(prefix="/api/sales-orders", tags=["sales"])


class LineIn(BaseModel):
    product_id: int
    qty: int = Field(gt=0, le=100_000)
    unit_price: int | None = Field(None, ge=0)
    discount_pct: int | None = Field(None, ge=0, le=100)


class OrderIn(BaseModel):
    customer_id: int
    warehouse_id: int
    order_date: date | None = None
    customer_ref: str | None = Field(None, max_length=60)
    note: str | None = Field(None, max_length=500)
    lines: list[LineIn] = Field(min_length=1, max_length=200)

    def to_service(self) -> svc.SalesOrderIn:
        return svc.SalesOrderIn(
            customer_id=self.customer_id, warehouse_id=self.warehouse_id, order_date=self.order_date or today(),
            customer_ref=self.customer_ref, note=self.note,
            lines=[svc.SalesLineIn(li.product_id, li.qty, li.unit_price, li.discount_pct) for li in self.lines])


class DeliverIn(BaseModel):
    delivery_date: date | None = None
    lines: dict[int, int] = Field(description="order line id -> quantity shipped now")


class InvoiceIn(BaseModel):
    invoice_date: date | None = None


def order_out(o: SalesOrder, detail: bool = False, db=None) -> dict:
    out = {
        "id": o.id, "number": o.number, "status": o.status, "invoice_status": svc.invoice_status(o),
        "customer": customer_ref(o.customer), "warehouse": warehouse_ref(o.warehouse), "order_date": o.order_date,
        "customer_ref": o.customer_ref, "source": o.source, "external_id": o.external_id,
        "gross": o.gross, "discount": o.gross - o.subtotal, "subtotal": o.subtotal, "tax_rate": o.tax_rate,
        "tax": o.tax, "total": o.total,
        "delivered_pct": round(100 * sum(li.qty_delivered for li in o.lines) / max(1, sum(li.qty for li in o.lines))),
    }
    if detail:
        stock = {}
        if o.status in ("draft", "confirmed", "partially_delivered"):
            # What the shipping warehouse can still promise, to warn before confirming or delivering.
            for li in o.lines:
                row = next((r for r in availability(db, li.product) if r["warehouse"]["id"] == o.warehouse_id), None)
                stock[li.id] = {"on_hand": row["on_hand"], "available": row["available"]} if row else None
        out.update({
            "note": o.note, "created_by": user_ref(o.created_by), "created_at": o.created_at,
            "lines": [{"id": li.id, "product": product_ref(li.product), "qty": li.qty, "unit_price": li.unit_price,
                       "discount_pct": li.discount_pct, "line_total": li.line_total,
                       "qty_delivered": li.qty_delivered, "qty_invoiced": li.qty_invoiced,
                       "stock": stock.get(li.id)} for li in o.lines],
            "deliveries": [{"id": d.id, "number": d.number, "delivery_date": d.delivery_date,
                            "units": sum(li.qty for li in d.lines), "created_by": user_ref(d.created_by),
                            "lines": [{"product": product_ref(li.product), "qty": li.qty} for li in d.lines]}
                           for d in o.deliveries],
            "invoices": [{"id": i.id, "number": i.number, "issue_date": i.issue_date, "due_date": i.due_date,
                          "status": i.status, "total": i.total, "balance": i.balance}
                         for i in db.scalars(select(Invoice).filter_by(sales_order_id=o.id).order_by(Invoice.id))],
            "activity": timeline(db, "sales_order", o.id),
        })
    return out


def _load(db, order_id: int) -> SalesOrder:
    order = db.scalar(select(SalesOrder).where(SalesOrder.id == order_id).options(
        selectinload(SalesOrder.lines).selectinload(SalesOrderLine.product),
        selectinload(SalesOrder.deliveries).selectinload(Delivery.lines).selectinload(DeliveryLine.product)))
    if order is None:
        get_or_404(db, SalesOrder, order_id, "Sales order")
    return order


@router.get("")
def list_orders(db: Db, _: can("sales.read"), params: Params, status: str | None = None,
                customer_id: int | None = None, date_from: date | None = None, date_to: date | None = None) -> dict:
    stmt = select(SalesOrder).join(SalesOrder.customer).options(
        selectinload(SalesOrder.customer), selectinload(SalesOrder.warehouse), selectinload(SalesOrder.lines))
    if status == "open":
        stmt = stmt.where(SalesOrder.status.in_(("confirmed", "partially_delivered")))
    elif status:
        stmt = stmt.where(SalesOrder.status == status)
    if customer_id:
        stmt = stmt.where(SalesOrder.customer_id == customer_id)
    if date_from:
        stmt = stmt.where(SalesOrder.order_date >= date_from)
    if date_to:
        stmt = stmt.where(SalesOrder.order_date <= date_to)
    if params.q:
        stmt = stmt.where(or_(SalesOrder.number.ilike(like(params.q)), Customer.name.ilike(like(params.q)),
                              SalesOrder.customer_ref.ilike(like(params.q))))
    return paginate(db, stmt, params, order_out,
                    sortable={"number": SalesOrder.number, "date": SalesOrder.order_date, "customer": Customer.name,
                              "total": SalesOrder.total},
                    default_sort=[SalesOrder.order_date.desc(), SalesOrder.id.desc()])


@router.get("/{order_id}")
def get_order(order_id: int, db: Db, _: can("sales.read")) -> dict:
    return order_out(_load(db, order_id), True, db)


@router.post("", status_code=201)
def create_order(body: OrderIn, db: Db, user: can("sales.write")) -> dict:
    order = svc.save_order(db, user, body.to_service())
    db.commit()
    return order_out(_load(db, order.id), True, db)


@router.put("/{order_id}")
def update_order(order_id: int, body: OrderIn, db: Db, user: can("sales.write")) -> dict:
    svc.save_order(db, user, body.to_service(), _load(db, order_id))
    db.commit()
    return order_out(_load(db, order_id), True, db)


@router.post("/{order_id}/confirm")
def confirm_order(order_id: int, db: Db, user: can("sales.write")) -> dict:
    svc.confirm(db, user, _load(db, order_id))
    db.commit()
    return order_out(_load(db, order_id), True, db)


@router.post("/{order_id}/cancel")
def cancel_order(order_id: int, db: Db, user: can("sales.write")) -> dict:
    svc.cancel(db, user, _load(db, order_id))
    db.commit()
    return order_out(_load(db, order_id), True, db)


@router.post("/{order_id}/deliver")
def deliver_order(order_id: int, body: DeliverIn, db: Db, user: can("sales.deliver")) -> dict:
    svc.deliver(db, user, _load(db, order_id), body.lines, body.delivery_date or today())
    db.commit()
    return order_out(_load(db, order_id), True, db)


@router.post("/{order_id}/invoice")
def invoice_order(order_id: int, body: InvoiceIn, db: Db, user: can("finance.write")) -> dict:
    invoice = svc.create_invoice(db, user, _load(db, order_id), body.invoice_date or today())
    db.commit()
    return {"id": invoice.id, "number": invoice.number}
