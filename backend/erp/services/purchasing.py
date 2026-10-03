"""Purchase orders: draft -> confirmed -> (partially_)received, then billed by the supplier."""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    GoodsReceipt,
    GoodsReceiptLine,
    Invoice,
    InvoiceLine,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    User,
    Warehouse,
    utcnow,
)
from .common import DomainError, at_noon, get_setting, line_amount, log, next_number, stamp, tax_amount
from .inventory import Ref, apply_receipt_cost, post_move


@dataclass
class PurchaseLineIn:
    product_id: int
    qty: int
    unit_cost: int


@dataclass
class PurchaseOrderIn:
    supplier_id: int
    warehouse_id: int
    order_date: date
    lines: list[PurchaseLineIn]
    expected_date: date | None = None
    supplier_ref: str | None = None
    note: str | None = None


def _recalculate(order: PurchaseOrder) -> None:
    for line in order.lines:
        line.line_total = line_amount(line.qty, line.unit_cost)
    order.subtotal = sum(li.line_total for li in order.lines)
    order.tax = tax_amount(order.subtotal, order.tax_rate)
    order.total = order.subtotal + order.tax


def save_order(db: Session, user: User, data: PurchaseOrderIn, order: PurchaseOrder | None = None) -> PurchaseOrder:
    """Create a draft, or replace a draft's header and lines."""
    if order is not None and order.status != "draft":
        raise DomainError(409, f"{order.number} is {order.status}; only drafts can be edited.")
    supplier = db.get(Supplier, data.supplier_id)
    if supplier is None or not supplier.active:
        raise DomainError(422, "Pick an active supplier.")
    warehouse = db.get(Warehouse, data.warehouse_id)
    if warehouse is None or not warehouse.active:
        raise DomainError(422, "Pick an active warehouse to receive into.")
    if not data.lines:
        raise DomainError(422, "Add at least one product.")
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_([li.product_id for li in data.lines])))}
    for li in data.lines:
        product = products.get(li.product_id)
        if product is None or not product.active:
            raise DomainError(422, f"Product {li.product_id} is unknown or inactive.")
        if li.qty <= 0 or li.unit_cost < 0:
            raise DomainError(422, f"{product.name}: quantity must be positive and cost not negative.")

    created = order is None
    if created:
        order = PurchaseOrder(number=next_number(db, "PO", data.order_date), created_at=stamp(data.order_date), created_by_id=user.id,
                              tax_rate=int(get_setting(db, "tax_rate")))
        db.add(order)
    order.supplier_id = supplier.id
    order.warehouse_id = warehouse.id
    order.order_date = data.order_date
    order.expected_date = data.expected_date
    order.supplier_ref = data.supplier_ref
    order.note = data.note
    order.lines = [PurchaseOrderLine(product_id=li.product_id, qty=li.qty, unit_cost=li.unit_cost, line_total=0)
                   for li in data.lines]
    _recalculate(order)
    db.flush()
    log(db, user, "purchase_order", order.id, "created" if created else "updated",
        f"{order.number} {'created' if created else 'updated'} for {supplier.name}", at=at_noon(data.order_date) if created else None)
    return order


def confirm(db: Session, user: User, order: PurchaseOrder) -> PurchaseOrder:
    if order.status != "draft":
        raise DomainError(409, f"{order.number} is already {order.status}.")
    order.status = "confirmed"
    order.confirmed_at = utcnow()
    log(db, user, "purchase_order", order.id, "confirmed", f"{order.number} sent to {order.supplier.name}", at=at_noon(order.order_date))
    return order


def cancel(db: Session, user: User, order: PurchaseOrder) -> PurchaseOrder:
    if order.status not in ("draft", "confirmed"):
        raise DomainError(409, f"{order.number} is {order.status}; goods were already received.")
    order.status = "cancelled"
    log(db, user, "purchase_order", order.id, "cancelled", f"{order.number} cancelled")
    return order


def receive(db: Session, user: User, order: PurchaseOrder, qty_by_line: dict[int, int], on: date) -> GoodsReceipt:
    """Book goods in: raises stock, updates average cost, advances the order status."""
    if order.status not in ("confirmed", "partially_received"):
        raise DomainError(409, f"{order.number} is {order.status}; only confirmed orders can be received.")
    lines = {li.id: li for li in order.lines}
    todo = {lid: q for lid, q in qty_by_line.items() if q}
    if not todo:
        raise DomainError(422, "Enter a quantity for at least one line.")
    for lid, qty in todo.items():
        line = lines.get(lid)
        if line is None:
            raise DomainError(422, f"Line {lid} is not on {order.number}.")
        if qty < 0 or qty > line.qty - line.qty_received:
            raise DomainError(422, f"{line.product.name}: receive between 1 and {line.qty - line.qty_received}.")

    receipt = GoodsReceipt(number=next_number(db, "GR", on), order_id=order.id, warehouse_id=order.warehouse_id,
                           receipt_date=on, created_at=stamp(on), created_by_id=user.id)
    db.add(receipt)
    db.flush()
    ref = Ref("goods_receipt", receipt.id, receipt.number)
    for lid, qty in todo.items():
        line = lines[lid]
        apply_receipt_cost(db, line.product, qty, line.unit_cost)
        post_move(db, product=line.product, warehouse=order.warehouse, qty=qty, kind="receipt",
                  unit_cost=line.unit_cost, ref=ref, user=user, at=at_noon(on))
        line.qty_received += qty
        receipt.lines.append(GoodsReceiptLine(order_line_id=line.id, product_id=line.product_id, qty=qty,
                                              unit_cost=line.unit_cost))
    order.status = "received" if all(li.qty_received == li.qty for li in order.lines) else "partially_received"
    log(db, user, "purchase_order", order.id, "received",
        f"{order.number}: {receipt.number}, {sum(todo.values())} unit(s) received into {order.warehouse.name}", at=at_noon(on))
    return receipt


def create_bill(db: Session, user: User, order: PurchaseOrder, on: date, supplier_ref: str | None = None) -> Invoice:
    """Supplier bill for everything received and not billed yet (three-way match: PO, receipt, bill)."""
    to_bill = [li for li in order.lines if li.qty_received > li.qty_billed]
    if not to_bill:
        raise DomainError(409, f"Nothing on {order.number} is received and unbilled.")
    bill = Invoice(number=next_number(db, "BILL", on), kind="supplier", supplier_id=order.supplier_id,
                   purchase_order_id=order.id, issue_date=on, created_at=stamp(on),
                   due_date=on + timedelta(days=order.supplier.payment_terms_days),
                   partner_ref=supplier_ref, tax_rate=order.tax_rate, created_by_id=user.id)
    for line in to_bill:
        qty = line.qty_received - line.qty_billed
        bill.lines.append(InvoiceLine(product_id=line.product_id, qty=qty, unit_price=line.unit_cost,
                                      line_total=line_amount(qty, line.unit_cost), purchase_order_line_id=line.id))
        line.qty_billed += qty
    bill.subtotal = sum(li.line_total for li in bill.lines)
    bill.tax = tax_amount(bill.subtotal, bill.tax_rate)
    bill.total = bill.subtotal + bill.tax
    db.add(bill)
    db.flush()
    log(db, user, "purchase_order", order.id, "billed", f"{order.number}: bill {bill.number} recorded", at=at_noon(on))
    log(db, user, "invoice", bill.id, "created", f"{bill.number} from {order.supplier.name} for {order.number}", at=at_noon(on))
    return bill


def billing_status(order: PurchaseOrder) -> str:
    billed = sum(li.qty_billed for li in order.lines)
    if billed == 0:
        return "not_billed"
    return "billed" if all(li.qty_billed == li.qty for li in order.lines) else "partially_billed"
