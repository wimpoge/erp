"""Customer invoices (receivables), supplier bills (payables) and payments."""

from datetime import date
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from ..models import Customer, Invoice, InvoiceLine, Payment, Supplier, today
from ..services import finance as svc
from ..services.common import DomainError, get_or_404
from .deps import Db, Params, can, like, paginate
from .serializers import customer_ref, product_ref, supplier_ref, timeline, user_ref

router = APIRouter(prefix="/api", tags=["finance"])


def invoice_out(i: Invoice, detail: bool = False, db=None) -> dict:
    on = today()
    out = {
        "id": i.id, "number": i.number, "kind": i.kind, "status": svc.display_status(i, on),
        "partner": customer_ref(i.customer) if i.kind == "customer" else supplier_ref(i.supplier),
        "issue_date": i.issue_date, "due_date": i.due_date, "days_overdue": max(0, (on - i.due_date).days)
        if i.status == "open" else 0,
        "partner_ref": i.partner_ref, "subtotal": i.subtotal, "tax_rate": i.tax_rate, "tax": i.tax, "total": i.total,
        "amount_paid": i.amount_paid, "balance": i.balance,
        "source": ({"type": "sales_order", "id": i.sales_order.id, "number": i.sales_order.number} if i.sales_order
                   else {"type": "purchase_order", "id": i.purchase_order.id, "number": i.purchase_order.number}
                   if i.purchase_order else None),
    }
    if detail:
        partner = i.customer if i.kind == "customer" else i.supplier
        out.update({
            # Full address block for the printed document.
            "partner_details": {"address": partner.address, "city": partner.city, "phone": partner.phone,
                                "email": partner.email, "payment_terms_days": partner.payment_terms_days},
            "created_by": user_ref(i.created_by), "created_at": i.created_at,
            "lines": [{"id": li.id, "product": product_ref(li.product), "qty": li.qty, "unit_price": li.unit_price,
                       "discount_pct": li.discount_pct, "line_total": li.line_total} for li in i.lines],
            "payments": [payment_out(p) for p in i.payments],
            "activity": timeline(db, "invoice", i.id),
        })
    return out


def payment_out(p: Payment) -> dict:
    return {"id": p.id, "number": p.number, "payment_date": p.payment_date, "amount": p.amount, "method": p.method,
            "reference": p.reference, "created_by": user_ref(p.created_by)}


_load = (selectinload(Invoice.customer), selectinload(Invoice.supplier), selectinload(Invoice.sales_order),
         selectinload(Invoice.purchase_order))


@router.get("/invoices")
def list_invoices(
    db: Db,
    _: can("finance.read"),
    params: Params,
    kind: Literal["customer", "supplier"] = "customer",
    status: Literal["unpaid", "overdue", "paid", "cancelled"] | None = None,
    partner_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    partner = Customer if kind == "customer" else Supplier
    stmt = (select(Invoice).where(Invoice.kind == kind).options(*_load)
            .outerjoin(partner, (Invoice.customer_id if kind == "customer" else Invoice.supplier_id) == partner.id))
    if status == "unpaid":
        stmt = stmt.where(Invoice.status == "open")
    elif status == "overdue":
        stmt = stmt.where(Invoice.status == "open", Invoice.due_date < today())
    elif status:
        stmt = stmt.where(Invoice.status == status)
    if partner_id:
        stmt = stmt.where((Invoice.customer_id if kind == "customer" else Invoice.supplier_id) == partner_id)
    if date_from:
        stmt = stmt.where(Invoice.issue_date >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.issue_date <= date_to)
    if params.q:
        stmt = stmt.where(or_(Invoice.number.ilike(like(params.q)), partner.name.ilike(like(params.q)),
                              Invoice.partner_ref.ilike(like(params.q))))
    return paginate(db, stmt, params, invoice_out,
                    sortable={"number": Invoice.number, "date": Invoice.issue_date, "due": Invoice.due_date,
                              "total": Invoice.total, "balance": Invoice.total - Invoice.amount_paid,
                              "partner": partner.name},
                    default_sort=[Invoice.issue_date.desc(), Invoice.id.desc()])


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, db: Db, _: can("finance.read")) -> dict:
    invoice = db.scalar(select(Invoice).where(Invoice.id == invoice_id).options(
        *_load, selectinload(Invoice.lines).selectinload(InvoiceLine.product), selectinload(Invoice.payments)))
    if invoice is None:
        raise DomainError(404, "Invoice not found.")
    return invoice_out(invoice, True, db)


class PaymentIn(BaseModel):
    amount: int = Field(gt=0)
    payment_date: date | None = None
    method: Literal["bank_transfer", "cash", "card", "qris"] = "bank_transfer"
    reference: str | None = Field(None, max_length=80)


@router.post("/invoices/{invoice_id}/payments", status_code=201)
def add_payment(invoice_id: int, body: PaymentIn, db: Db, user: can("finance.write")) -> dict:
    invoice = get_or_404(db, Invoice, invoice_id, "Invoice")
    svc.register_payment(db, user, invoice, body.amount, body.payment_date or today(), body.method, body.reference)
    db.commit()
    return get_invoice(invoice_id, db, user)


@router.post("/invoices/{invoice_id}/cancel")
def cancel_invoice(invoice_id: int, db: Db, user: can("finance.write")) -> dict:
    svc.cancel_invoice(db, user, get_or_404(db, Invoice, invoice_id, "Invoice"))
    db.commit()
    return get_invoice(invoice_id, db, user)


@router.get("/payments")
def list_payments(db: Db, _: can("finance.read"), params: Params,
                  kind: Literal["customer", "supplier"] | None = None) -> dict:
    stmt = select(Payment).join(Payment.invoice).options(
        selectinload(Payment.invoice).selectinload(Invoice.customer),
        selectinload(Payment.invoice).selectinload(Invoice.supplier), selectinload(Payment.created_by))
    if kind:
        stmt = stmt.where(Invoice.kind == kind)
    if params.q:
        stmt = stmt.where(or_(Payment.number.ilike(like(params.q)), Invoice.number.ilike(like(params.q)),
                              Payment.reference.ilike(like(params.q))))

    def row(p: Payment) -> dict:
        inv = p.invoice
        return {**payment_out(p), "direction": "in" if inv.kind == "customer" else "out",
                "invoice": {"id": inv.id, "number": inv.number, "kind": inv.kind},
                "partner": customer_ref(inv.customer) if inv.kind == "customer" else supplier_ref(inv.supplier)}

    return paginate(db, stmt, params, row, sortable={"date": Payment.payment_date, "amount": Payment.amount},
                    default_sort=[Payment.payment_date.desc(), Payment.id.desc()])
