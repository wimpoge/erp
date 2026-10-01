"""Selling at the till and pushing paid orders to the ERP.

The till never waits for the ERP: an order is committed locally first and pushed
afterwards. Pushes are idempotent (the ERP is asked for our external id before we
create anything) and failed pushes are retried with exponential backoff.
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from .erp_client import ErpClient, ErpError
from .models import (
    Customer,
    Location,
    Order,
    OrderLine,
    Payment,
    Product,
    ProductStock,
    PushAttempt,
    Register,
    utcnow,
)


class OrderError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class LineIn(BaseModel):
    product_id: int
    qty: int = Field(gt=0, le=999)


class PaymentIn(BaseModel):
    method: Literal["cash", "card", "qris"]
    amount: int = Field(gt=0)


class OrderIn(BaseModel):
    location_id: int
    register_id: int | None = None
    customer_id: int | None = None
    lines: list[LineIn] = Field(min_length=1)
    payments: list[PaymentIn] = Field(min_length=1)


def create_order(db: Session, data: OrderIn) -> Order:
    location = db.get(Location, data.location_id)
    if location is None or not location.active:
        raise OrderError(404, "store not found")
    register = None
    if data.register_id is not None:
        register = db.get(Register, data.register_id)
        if register is None or register.location_id != location.id or not register.active:
            raise OrderError(422, "register does not belong to this store")
    customer = None
    if data.customer_id is not None:
        customer = db.get(Customer, data.customer_id)
        if customer is None or not customer.active:
            raise OrderError(404, "customer not found")

    qty_by_product: dict[int, int] = defaultdict(int)
    for line in data.lines:
        qty_by_product[line.product_id] += line.qty

    order = Order(location=location, register=register, customer=customer, subtotal=0, total=0, paid=0)
    for product_id, qty in qty_by_product.items():
        product = db.get(Product, product_id)
        if product is None or not product.active:
            raise OrderError(404, f"product {product_id} not found")
        stock = db.scalar(
            select(ProductStock).filter_by(product_id=product_id, location_id=location.id).with_for_update()
        )
        if stock is None or stock.on_hand < qty:
            available = stock.on_hand if stock else 0
            raise OrderError(409, f"only {available} x {product.name} in stock")
        stock.on_hand -= qty
        # Prices come from the synced catalogue, never from the client.
        order.lines.append(OrderLine(product=product, qty=qty, unit_price=product.price,
                                     line_total=qty * product.price))

    order.subtotal = sum(line.line_total for line in order.lines)
    rate = customer.group.discount_rate if customer and customer.group and customer.group.active else 0
    order.discount = order.subtotal * rate // 100
    order.total = order.subtotal - order.discount

    order.paid = sum(p.amount for p in data.payments)
    cash = sum(p.amount for p in data.payments if p.method == "cash")
    if order.paid < order.total:
        raise OrderError(422, f"payments {order.paid} do not cover total {order.total}")
    order.change = order.paid - order.total
    if order.change > cash:
        raise OrderError(422, "only cash payments can give change")
    order.payments = [Payment(method=p.method, amount=p.amount) for p in data.payments]

    day_start = datetime.combine(utcnow().date(), datetime.min.time())
    count_today = db.scalar(
        select(func.count()).select_from(Order).where(
            Order.location_id == location.id,
            Order.created_at >= day_start,
            Order.created_at < day_start + timedelta(days=1),
        )
    )
    order.number = f"{location.code}-{day_start:%Y%m%d}-{count_today + 1:04d}"
    db.add(order)
    db.commit()
    return order


# ---------------------------------------------------------------- pushing to the ERP


def push_payload(order: Order) -> dict:
    return {
        "external_id": order.external_id,
        "store_id": str(order.location.erp_public_id),
        "register_id": str(order.register.erp_public_id) if order.register else None,
        "customer_id": str(order.customer.erp_public_id) if order.customer else None,
        "discount": order.discount,
        "ordered_at": order.created_at.isoformat(),
        "lines": [
            {"product_id": str(line.product.erp_public_id), "qty": line.qty, "unit_price": line.unit_price}
            for line in order.lines
        ],
    }


def backoff(attempt: int) -> timedelta:
    return timedelta(minutes=min(2 ** (attempt - 1), 60))  # 1, 2, 4, ... 60 minutes


def push_order(db: Session, erp: ErpClient, order: Order, max_attempts: int) -> Order:
    if order.push_status == "sent":
        return order
    order.push_attempts += 1
    status_code = None
    try:
        # Look first: an earlier attempt may have reached the ERP even though we never saw the answer.
        found = erp.request("GET", "/api/sales-orders", params={"external_id": order.external_id})["items"]
        erp_order = found[0] if found else erp.request("POST", "/api/sales-orders", json=push_payload(order))
    except (ErpError, httpx.HTTPError) as exc:
        retryable = not isinstance(exc, ErpError) or exc.retryable
        status_code = exc.status_code if isinstance(exc, ErpError) else None
        order.last_push_error = str(exc)[:500]
        if retryable and order.push_attempts < max_attempts:
            order.next_push_at = utcnow() + backoff(order.push_attempts)
        else:
            order.push_status = "failed"
            order.next_push_at = None
        order.push_log.append(PushAttempt(attempt=order.push_attempts, ok=False,
                                          status_code=status_code, error=order.last_push_error))
    else:
        order.push_status = "sent"
        order.erp_public_id = uuid.UUID(erp_order["id"])
        order.erp_number = erp_order["number"]
        order.next_push_at = None
        order.last_push_error = None
        order.push_log.append(PushAttempt(attempt=order.push_attempts, ok=True, status_code=200, error=None))
    db.commit()
    return order


def _load():
    return select(Order).options(
        selectinload(Order.location), selectinload(Order.register), selectinload(Order.customer),
        selectinload(Order.lines).selectinload(OrderLine.product), selectinload(Order.push_log),
    )


def push_order_by_id(session_factory: sessionmaker, erp: ErpClient, order_id: int, max_attempts: int) -> None:
    """Background task run after the sale's response has gone back to the till."""
    with session_factory() as db:
        order = db.scalar(_load().where(Order.id == order_id))
        if order is not None:
            push_order(db, erp, order, max_attempts)


def push_due(db: Session, erp: ErpClient, max_attempts: int, limit: int = 100) -> dict:
    """Retry every pending order whose backoff has passed. Safe to run from several workers."""
    now = utcnow()
    orders = db.scalars(
        _load()
        .where(Order.push_status == "pending")
        .where((Order.next_push_at.is_(None)) | (Order.next_push_at <= now))
        .order_by(Order.id)
        .limit(limit)
        .with_for_update(skip_locked=True, of=Order)
    ).all()
    counts = {"tried": len(orders), "sent": 0, "pending": 0, "failed": 0}
    for order in orders:
        counts[push_order(db, erp, order, max_attempts).push_status] += 1
    return counts
