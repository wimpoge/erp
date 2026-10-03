"""Sales orders: draft -> confirmed (credit check) -> (partially_)delivered, then invoiced."""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Customer,
    Delivery,
    DeliveryLine,
    Invoice,
    InvoiceLine,
    Product,
    SalesOrder,
    SalesOrderLine,
    User,
    Warehouse,
    utcnow,
)
from .common import DomainError, at_noon, get_setting, line_amount, log, next_number, rupiah, stamp, tax_amount
from .inventory import OPEN_SALES, Ref, post_move


@dataclass
class SalesLineIn:
    product_id: int
    qty: int
    unit_price: int | None = None  # None: the product's list price
    discount_pct: int | None = None  # None: the customer group's discount


@dataclass
class SalesOrderIn:
    customer_id: int
    warehouse_id: int
    order_date: date
    lines: list[SalesLineIn]
    customer_ref: str | None = None
    note: str | None = None


def _recalculate(order: SalesOrder) -> None:
    for line in order.lines:
        line.line_total = line_amount(line.qty, line.unit_price, line.discount_pct)
    order.gross = sum(li.qty * li.unit_price for li in order.lines)
    order.subtotal = sum(li.line_total for li in order.lines)
    order.tax = tax_amount(order.subtotal, order.tax_rate)
    order.total = order.subtotal + order.tax


def save_order(db: Session, user: User | None, data: SalesOrderIn, order: SalesOrder | None = None,
               external_id: str | None = None) -> SalesOrder:
    """Create a draft, or replace a draft's header and lines."""
    if order is not None and order.status != "draft":
        raise DomainError(409, f"{order.number} is {order.status}; only drafts can be edited.")
    customer = db.get(Customer, data.customer_id)
    if customer is None or not customer.active:
        raise DomainError(422, "Pick an active customer.")
    warehouse = db.get(Warehouse, data.warehouse_id)
    if warehouse is None or not warehouse.active:
        raise DomainError(422, "Pick an active warehouse to ship from.")
    if not data.lines:
        raise DomainError(422, "Add at least one product.")
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_([li.product_id for li in data.lines])))}
    default_discount = customer.group.discount_pct if customer.group else 0
    lines = []
    for li in data.lines:
        product = products.get(li.product_id)
        if product is None or not product.active:
            raise DomainError(422, f"Product {li.product_id} is unknown or inactive.")
        discount = default_discount if li.discount_pct is None else li.discount_pct
        price = product.sale_price if li.unit_price is None else li.unit_price
        if li.qty <= 0 or price < 0 or not 0 <= discount <= 100:
            raise DomainError(422, f"{product.name}: check quantity, price and discount.")
        lines.append(SalesOrderLine(product_id=product.id, qty=li.qty, unit_price=price, discount_pct=discount,
                                    line_total=0))

    created = order is None
    if created:
        order = SalesOrder(number=next_number(db, "SO", data.order_date), created_at=stamp(data.order_date), created_by_id=user.id if user else None,
                           tax_rate=int(get_setting(db, "tax_rate")), source="api" if external_id else "manual",
                           external_id=external_id)
        db.add(order)
    order.customer_id = customer.id
    order.warehouse_id = warehouse.id
    order.order_date = data.order_date
    order.customer_ref = data.customer_ref
    order.note = data.note
    order.lines = lines
    _recalculate(order)
    db.flush()
    log(db, user, "sales_order", order.id, "created" if created else "updated",
        f"{order.number} {'created' if created else 'updated'} for {customer.name}"
        + (" via integration API" if external_id else ""), at=at_noon(data.order_date) if created else None)
    return order


def credit_exposure(db: Session, customer_id: int, exclude_order_id: int | None = None) -> int:
    """What the customer owes plus what they have ordered and not been invoiced for yet."""
    open_invoices = db.scalar(
        select(func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0))
        .where(Invoice.kind == "customer", Invoice.customer_id == customer_id, Invoice.status == "open")
    )
    stmt = (
        select(SalesOrder)
        .where(SalesOrder.customer_id == customer_id, SalesOrder.status.in_(OPEN_SALES + ("delivered",)))
    )
    uninvoiced = 0
    for order in db.scalars(stmt):
        if order.id == exclude_order_id:
            continue
        for li in order.lines:
            remaining = li.qty - li.qty_invoiced
            if remaining:
                amount = line_amount(remaining, li.unit_price, li.discount_pct)
                uninvoiced += amount + tax_amount(amount, order.tax_rate)
    return open_invoices + uninvoiced


def confirm(db: Session, user: User | None, order: SalesOrder) -> SalesOrder:
    if order.status != "draft":
        raise DomainError(409, f"{order.number} is already {order.status}.")
    customer = order.customer
    if customer.credit_limit > 0:
        exposure = credit_exposure(db, customer.id, exclude_order_id=order.id)
        if exposure + order.total > customer.credit_limit:
            raise DomainError(
                409,
                f"Credit limit exceeded for {customer.name}: limit {rupiah(customer.credit_limit)}, "
                f"already open {rupiah(exposure)}, this order {rupiah(order.total)}.",
            )
    order.status = "confirmed"
    order.confirmed_at = utcnow()
    log(db, user, "sales_order", order.id, "confirmed", f"{order.number} confirmed for {customer.name}", at=at_noon(order.order_date))
    return order


def cancel(db: Session, user: User, order: SalesOrder) -> SalesOrder:
    if order.status not in ("draft", "confirmed"):
        raise DomainError(409, f"{order.number} is {order.status}; goods were already shipped.")
    order.status = "cancelled"
    log(db, user, "sales_order", order.id, "cancelled", f"{order.number} cancelled")
    return order


def deliver(db: Session, user: User | None, order: SalesOrder, qty_by_line: dict[int, int], on: date) -> Delivery:
    """Ship goods: lowers stock at the order's warehouse and records the cost of goods sold."""
    if order.status not in ("confirmed", "partially_delivered"):
        raise DomainError(409, f"{order.number} is {order.status}; only confirmed orders can be delivered.")
    lines = {li.id: li for li in order.lines}
    todo = {lid: q for lid, q in qty_by_line.items() if q}
    if not todo:
        raise DomainError(422, "Enter a quantity for at least one line.")
    for lid, qty in todo.items():
        line = lines.get(lid)
        if line is None:
            raise DomainError(422, f"Line {lid} is not on {order.number}.")
        if qty < 0 or qty > line.qty - line.qty_delivered:
            raise DomainError(422, f"{line.product.name}: deliver between 1 and {line.qty - line.qty_delivered}.")

    delivery = Delivery(number=next_number(db, "DO", on), order_id=order.id, warehouse_id=order.warehouse_id,
                        delivery_date=on, created_at=stamp(on), created_by_id=user.id if user else None)
    db.add(delivery)
    db.flush()
    ref = Ref("delivery", delivery.id, delivery.number)
    for lid, qty in todo.items():
        line = lines[lid]
        cost = line.product.avg_cost
        post_move(db, product=line.product, warehouse=order.warehouse, qty=-qty, kind="delivery", unit_cost=cost,
                  ref=ref, user=user, at=at_noon(on))
        line.qty_delivered += qty
        delivery.lines.append(DeliveryLine(order_line_id=line.id, product_id=line.product_id, qty=qty, unit_cost=cost))
    order.status = "delivered" if all(li.qty_delivered == li.qty for li in order.lines) else "partially_delivered"
    log(db, user, "sales_order", order.id, "delivered",
        f"{order.number}: {delivery.number}, {sum(todo.values())} unit(s) shipped from {order.warehouse.name}", at=at_noon(on))
    return delivery


def create_invoice(db: Session, user: User | None, order: SalesOrder, on: date) -> Invoice:
    """Invoice everything delivered and not invoiced yet."""
    to_invoice = [li for li in order.lines if li.qty_delivered > li.qty_invoiced]
    if not to_invoice:
        raise DomainError(409, f"Nothing on {order.number} is delivered and not invoiced.")
    invoice = Invoice(number=next_number(db, "INV", on), kind="customer", customer_id=order.customer_id,
                      sales_order_id=order.id, issue_date=on, created_at=stamp(on),
                      due_date=on + timedelta(days=order.customer.payment_terms_days),
                      partner_ref=order.customer_ref, tax_rate=order.tax_rate, created_by_id=user.id if user else None)
    for line in to_invoice:
        qty = line.qty_delivered - line.qty_invoiced
        invoice.lines.append(InvoiceLine(product_id=line.product_id, qty=qty, unit_price=line.unit_price,
                                         discount_pct=line.discount_pct,
                                         line_total=line_amount(qty, line.unit_price, line.discount_pct),
                                         sales_order_line_id=line.id))
        line.qty_invoiced += qty
    invoice.subtotal = sum(li.line_total for li in invoice.lines)
    invoice.tax = tax_amount(invoice.subtotal, invoice.tax_rate)
    invoice.total = invoice.subtotal + invoice.tax
    db.add(invoice)
    db.flush()
    log(db, user, "sales_order", order.id, "invoiced", f"{order.number}: invoice {invoice.number} issued", at=at_noon(on))
    log(db, user, "invoice", invoice.id, "created", f"{invoice.number} issued to {order.customer.name} for {order.number}",
        at=at_noon(on))
    return invoice


def invoice_status(order: SalesOrder) -> str:
    invoiced = sum(li.qty_invoiced for li in order.lines)
    if invoiced == 0:
        return "not_invoiced"
    return "invoiced" if all(li.qty_invoiced == li.qty for li in order.lines) else "partially_invoiced"
