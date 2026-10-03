"""Read-only figures for the dashboard and reports. Months are bucketed in Python so the
same code runs on SQLite (tests, local) and Postgres (production)."""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Category,
    Customer,
    Delivery,
    DeliveryLine,
    Invoice,
    InvoiceLine,
    Product,
    PurchaseOrder,
    SalesOrder,
    SalesReturn,
    SalesReturnLine,
    StockLevel,
    Warehouse,
)
from .inventory import OPEN_PURCHASES, OPEN_SALES


def month_start(on: date, back: int = 0) -> date:
    """First day of the month `back` months before `on`."""
    index = on.year * 12 + on.month - 1 - back
    return date(index // 12, index % 12 + 1, 1)


def _month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def _invoiced(db: Session, kind: str, start: date, end: date | None = None) -> int:
    """Invoiced before tax; for customers, less what came back as returns."""
    stmt = select(func.coalesce(func.sum(Invoice.subtotal), 0)).where(
        Invoice.kind == kind, Invoice.status != "cancelled", Invoice.issue_date >= start)
    if end:
        stmt = stmt.where(Invoice.issue_date < end)
    amount = db.scalar(stmt)
    if kind == "customer":
        returned = select(func.coalesce(func.sum(SalesReturn.subtotal), 0)).where(SalesReturn.return_date >= start)
        if end:
            returned = returned.where(SalesReturn.return_date < end)
        amount -= db.scalar(returned)
    return amount


def _cogs(db: Session, start: date, end: date | None = None) -> int:
    """Cost of goods shipped, less the cost of goods that came back."""
    stmt = select(func.coalesce(func.sum(DeliveryLine.qty * DeliveryLine.unit_cost), 0)).join(Delivery).where(
        Delivery.delivery_date >= start)
    returned = (select(func.coalesce(func.sum(SalesReturnLine.qty * SalesReturnLine.unit_cost), 0))
                .join(SalesReturn).where(SalesReturn.return_date >= start))
    if end:
        stmt = stmt.where(Delivery.delivery_date < end)
        returned = returned.where(SalesReturn.return_date < end)
    return db.scalar(stmt) - db.scalar(returned)


def _open_balance(db: Session, kind: str, overdue_before: date | None = None) -> tuple[int, int]:
    stmt = select(func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0), func.count()).where(
        Invoice.kind == kind, Invoice.status == "open")
    if overdue_before:
        stmt = stmt.where(Invoice.due_date < overdue_before)
    amount, count = db.execute(stmt).one()
    return amount, count


def stock_value(db: Session) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(StockLevel.on_hand * Product.avg_cost), 0)).join(Product)
    )


def low_stock(db: Session, limit: int = 10) -> list[dict]:
    on_hand = func.coalesce(func.sum(StockLevel.on_hand), 0)
    stmt = (
        select(Product, on_hand.label("on_hand"))
        .outerjoin(StockLevel, StockLevel.product_id == Product.id)
        .where(Product.active, Product.reorder_point > 0)
        .group_by(Product.id)
        .having(on_hand <= Product.reorder_point)
        .order_by((on_hand - Product.reorder_point).asc())
        .limit(limit)
    )
    return [{"id": p.id, "sku": p.sku, "name": p.name, "on_hand": qty, "reorder_point": p.reorder_point}
            for p, qty in db.execute(stmt)]


def dashboard(db: Session, on: date) -> dict:
    # Rolling 30 days rather than the calendar month: never looks empty on the 1st.
    period_start, prev_start = on - timedelta(days=29), on - timedelta(days=59)
    revenue = _invoiced(db, "customer", period_start)
    revenue_prev = _invoiced(db, "customer", prev_start, period_start)
    cogs = _cogs(db, period_start)
    ar, ar_count = _open_balance(db, "customer")
    ar_overdue, ar_overdue_count = _open_balance(db, "customer", on)
    ap, ap_count = _open_balance(db, "supplier")
    ap_overdue, ap_overdue_count = _open_balance(db, "supplier", on)
    return {
        "revenue_30d": revenue,
        "revenue_prev_30d": revenue_prev,
        "gross_profit_30d": revenue - cogs,
        "receivables": {"amount": ar, "count": ar_count, "overdue": ar_overdue, "overdue_count": ar_overdue_count},
        "payables": {"amount": ap, "count": ap_count, "overdue": ap_overdue, "overdue_count": ap_overdue_count},
        "stock_value": stock_value(db),
        "orders_to_deliver": db.scalar(select(func.count()).select_from(SalesOrder).where(SalesOrder.status.in_(OPEN_SALES))),
        "orders_to_receive": db.scalar(
            select(func.count()).select_from(PurchaseOrder).where(PurchaseOrder.status.in_(OPEN_PURCHASES))),
        "low_stock": low_stock(db, 8),
        "monthly": monthly(db, on, 12),
        "top_products": top_products(db, month_start(on, 2), 5),
    }


def monthly(db: Session, on: date, months: int) -> list[dict]:
    start = month_start(on, months - 1)
    buckets = {_month_key(month_start(on, back)): {"revenue": 0, "cogs": 0, "purchases": 0}
               for back in range(months - 1, -1, -1)}
    for kind, field in (("customer", "revenue"), ("supplier", "purchases")):
        rows = db.execute(select(Invoice.issue_date, Invoice.subtotal).where(
            Invoice.kind == kind, Invoice.status != "cancelled", Invoice.issue_date >= start))
        for d, amount in rows:
            buckets[_month_key(d)][field] += amount
    for d, amount in db.execute(
        select(Delivery.delivery_date, DeliveryLine.qty * DeliveryLine.unit_cost).join(Delivery)
        .where(Delivery.delivery_date >= start)
    ):
        buckets[_month_key(d)]["cogs"] += amount
    for d, amount in db.execute(select(SalesReturn.return_date, SalesReturn.subtotal).where(SalesReturn.return_date >= start)):
        buckets[_month_key(d)]["revenue"] -= amount
    for d, amount in db.execute(
        select(SalesReturn.return_date, SalesReturnLine.qty * SalesReturnLine.unit_cost).join(SalesReturn)
        .where(SalesReturn.return_date >= start)
    ):
        buckets[_month_key(d)]["cogs"] -= amount
    return [{"month": k, **v, "gross_profit": v["revenue"] - v["cogs"]} for k, v in buckets.items()]


def top_products(db: Session, since: date, limit: int = 10) -> list[dict]:
    revenue = func.sum(InvoiceLine.line_total)
    stmt = (
        select(Product.id, Product.sku, Product.name, func.sum(InvoiceLine.qty), revenue)
        .join(InvoiceLine.invoice).join(InvoiceLine.product)
        .where(Invoice.kind == "customer", Invoice.status != "cancelled", Invoice.issue_date >= since)
        .group_by(Product.id, Product.sku, Product.name)
        .order_by(revenue.desc())
        .limit(limit)
    )
    return [{"id": i, "sku": s, "name": n, "qty": q, "revenue": r} for i, s, n, q, r in db.execute(stmt)]


def top_customers(db: Session, since: date, limit: int = 10) -> list[dict]:
    revenue = func.sum(Invoice.subtotal)
    stmt = (
        select(Customer.id, Customer.code, Customer.name, func.count(Invoice.id), revenue)
        .join(Invoice, Invoice.customer_id == Customer.id)
        .where(Invoice.kind == "customer", Invoice.status != "cancelled", Invoice.issue_date >= since)
        .group_by(Customer.id, Customer.code, Customer.name)
        .order_by(revenue.desc())
        .limit(limit)
    )
    return [{"id": i, "code": c, "name": n, "invoices": k, "revenue": r} for i, c, n, k, r in db.execute(stmt)]


def sales_by_category(db: Session, since: date) -> list[dict]:
    revenue = func.sum(InvoiceLine.line_total)
    stmt = (
        select(func.coalesce(Category.name, "Uncategorised"), revenue)
        .select_from(InvoiceLine).join(InvoiceLine.invoice).join(InvoiceLine.product)
        .outerjoin(Category, Product.category_id == Category.id)
        .where(Invoice.kind == "customer", Invoice.status != "cancelled", Invoice.issue_date >= since)
        .group_by(Category.name)
        .order_by(revenue.desc())
    )
    return [{"category": c, "revenue": r} for c, r in db.execute(stmt)]


def stock_by_warehouse(db: Session) -> list[dict]:
    stmt = (
        select(Warehouse.id, Warehouse.code, Warehouse.name,
               func.coalesce(func.sum(StockLevel.on_hand), 0),
               func.coalesce(func.sum(StockLevel.on_hand * Product.avg_cost), 0))
        .outerjoin(StockLevel, StockLevel.warehouse_id == Warehouse.id)
        .outerjoin(Product, Product.id == StockLevel.product_id)
        .where(Warehouse.active)
        .group_by(Warehouse.id, Warehouse.code, Warehouse.name)
        .order_by(Warehouse.code)
    )
    return [{"id": i, "code": c, "name": n, "units": u, "value": v} for i, c, n, u, v in db.execute(stmt)]


AGING_BUCKETS = (("current", None, 0), ("1-30", 1, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("90+", 91, None))


def aging(db: Session, kind: str, on: date) -> dict:
    """Open balances by days past due, in total and per partner."""
    totals = {name: 0 for name, _, _ in AGING_BUCKETS}
    partners: dict[int, dict] = defaultdict(lambda: {"name": "", **{name: 0 for name, _, _ in AGING_BUCKETS}, "total": 0})
    partner_col = Invoice.customer_id if kind == "customer" else Invoice.supplier_id
    stmt = select(Invoice).where(Invoice.kind == kind, Invoice.status == "open")
    for inv in db.scalars(stmt):
        late = (on - inv.due_date).days
        bucket = next(name for name, low, high in AGING_BUCKETS
                      if (low is None and late <= 0) or (low is not None and late >= low and (high is None or late <= high)))
        balance = inv.balance
        totals[bucket] += balance
        partner = inv.customer if kind == "customer" else inv.supplier
        row = partners[getattr(inv, partner_col.key)]
        row["id"], row["name"] = partner.id, partner.name
        row[bucket] += balance
        row["total"] += balance
    rows = sorted(partners.values(), key=lambda r: r["total"], reverse=True)
    return {"buckets": [name for name, _, _ in AGING_BUCKETS], "totals": totals, "partners": rows}
