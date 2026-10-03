"""Receivables and payables: payments against invoices and bills."""

from datetime import date

from sqlalchemy.orm import Session

from ..models import Invoice, Payment, PurchaseOrderLine, SalesOrderLine, User
from .common import DomainError, at_noon, log, next_number, rupiah, stamp

PAYMENT_METHODS = ("bank_transfer", "cash", "card", "qris")


def display_status(invoice: Invoice, on: date) -> str:
    """open / partially_paid / overdue / paid / cancelled, as people talk about invoices."""
    if invoice.status != "open":
        return invoice.status
    if invoice.due_date < on:
        return "overdue"
    return "partially_paid" if invoice.amount_paid else "open"


def register_payment(db: Session, user: User | None, invoice: Invoice, amount: int, on: date, method: str,
                     reference: str | None = None) -> Payment:
    if invoice.status != "open":
        raise DomainError(409, f"{invoice.number} is {invoice.status}.")
    if method not in PAYMENT_METHODS:
        raise DomainError(422, f"Payment method must be one of: {', '.join(PAYMENT_METHODS)}.")
    if amount <= 0 or amount > invoice.balance:
        raise DomainError(422, f"Amount must be between 1 and the open balance of {rupiah(invoice.balance)}.")
    if on < invoice.issue_date:
        raise DomainError(422, "A payment cannot be dated before the invoice.")
    prefix = "RCV" if invoice.kind == "customer" else "PAY"
    payment = Payment(number=next_number(db, prefix, on), invoice_id=invoice.id, payment_date=on, created_at=stamp(on), amount=amount,
                      method=method, reference=reference, created_by_id=user.id if user else None)
    db.add(payment)
    invoice.amount_paid += amount
    if invoice.balance == 0:
        invoice.status = "paid"
    db.flush()
    verb = "received" if invoice.kind == "customer" else "paid"
    log(db, user, "invoice", invoice.id, "payment", f"{invoice.number}: {payment.number}, {rupiah(amount)} {verb} by {method.replace('_', ' ')}",
        at=at_noon(on))
    return payment


def cancel_invoice(db: Session, user: User, invoice: Invoice) -> Invoice:
    """Void an invoice nobody has paid on; its quantities can be invoiced again."""
    if invoice.status != "open" or invoice.amount_paid:
        raise DomainError(409, "Only an open invoice without payments can be cancelled.")
    for line in invoice.lines:
        if invoice.kind == "customer" and line.sales_order_line_id:
            db.get(SalesOrderLine, line.sales_order_line_id).qty_invoiced -= line.qty
        elif invoice.kind == "supplier" and line.purchase_order_line_id:
            db.get(PurchaseOrderLine, line.purchase_order_line_id).qty_billed -= line.qty
    invoice.status = "cancelled"
    log(db, user, "invoice", invoice.id, "cancelled", f"{invoice.number} cancelled; its quantities can be invoiced again")
    return invoice
