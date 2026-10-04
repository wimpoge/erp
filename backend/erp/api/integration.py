"""Integration API for outside systems (a POS, a web shop).

Client-credentials tokens, paginated lists that expose only public UUIDs, and a sales
order import that is idempotent on the caller's `external_id`, so a retried request
never creates a second order. An import that carries `payments` is a till sale: the
order is confirmed, shipped, invoiced and paid in one transaction, or not at all.
Returns follow the same rule: one external_id, one booking.
"""

import hmac
import secrets
import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ..models import (
    ApiClient,
    ApiToken,
    Customer,
    Invoice,
    Product,
    Promotion,
    SalesOrder,
    SalesOrderLine,
    SalesReturn,
    StockLevel,
    User,
    Warehouse,
    today,
    utcnow,
)
from ..permissions import ROLES, permissions_for
from ..services import auth as auth_svc
from ..services import finance as finance_svc
from ..services import inventory as inventory_svc
from ..services import sales as sales_svc
from ..services.promotions import current_promotions
from ..services.auth import sha256
from ..services.common import DomainError, all_settings, log, next_number, rupiah
from .deps import Db, Params, paginate

router = APIRouter(prefix="/api/integration/v1", tags=["integration API"])

# Grows when the API gains something a caller may want to check for before relying on it.
API_FEATURES = ["paid_sales", "line_discounts", "customer_create", "cashier_login", "supervisors", "returns",
                "promotions", "loyalty", "stock_requests", "cashier_profile"]


class TokenIn(BaseModel):
    grant_type: str = "client_credentials"
    client_id: str
    client_secret: str


@router.post("/token")
def issue_token(body: TokenIn, request: Request, db: Db) -> dict:
    client = db.scalar(select(ApiClient).filter_by(client_id=body.client_id, active=True))
    if body.grant_type != "client_credentials" or client is None or not hmac.compare_digest(
            client.secret_hash, sha256(body.client_secret)):
        raise HTTPException(401, "invalid_client")
    ttl = request.app.state.settings.integration_token_ttl_seconds
    token = secrets.token_urlsafe(32)
    db.add(ApiToken(token_hash=sha256(token), client_id=client.id, expires_at=utcnow() + timedelta(seconds=ttl)))
    client.last_used_at = utcnow()
    db.commit()
    return {"access_token": token, "token_type": "bearer", "expires_in": ttl}


def api_client(db: Db, authorization: Annotated[str | None, Header()] = None) -> ApiClient:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = db.get(ApiToken, sha256(authorization.removeprefix("Bearer ")))
    if token is None or token.expires_at < utcnow() or not token.client.active:
        raise HTTPException(401, "invalid or expired token")
    return token.client


Client = Annotated[ApiClient, Depends(api_client)]


@router.get("/settings")
def company_settings(db: Db, _: Client) -> dict:
    """What a till needs to price and print like the ERP: tax rate, currency and the receipt header."""
    s = all_settings(db)
    keys = ("company_name", "company_address", "company_phone", "company_tax_id", "tax_rate", "currency")
    return {**{k: s[k] for k in keys}, "features": API_FEATURES,
            "loyalty": {"earn_per": s["loyalty_earn_per"], "point_value": s["loyalty_point_value"]}}


class CashierLogin(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=200)


@router.post("/cashiers/login")
def cashier_login(body: CashierLogin, db: Db, _: Client) -> dict:
    """A till checks a cashier's username and password here: cashier accounts live in the ERP.
    Same lockout as the ERP's own login; only the cashier role may sell."""
    user = auth_svc.authenticate(db, body.username, body.password)
    if "pos.sell" not in permissions_for(user.role):
        raise DomainError(403, "Only cashier accounts can use the POS. Ask an administrator for one.")
    db.commit()  # last login, cleared failure count
    return {"username": user.username, "full_name": user.full_name, "email": user.email}


def cashier_out(user) -> dict:
    return {"username": user.username, "full_name": user.full_name, "email": user.email,
            "role": ROLES.get(user.role, {}).get("label", user.role), "active": user.active,
            "created_at": user.created_at, "last_login_at": user.last_login_at}


@router.get("/cashiers/{username}")
def cashier_profile(username: str, db: Db, _: Client) -> dict:
    """A cashier's account as the ERP holds it, for their profile page at the till."""
    user = db.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
    if user is None or "pos.sell" not in permissions_for(user.role):
        raise HTTPException(404, "cashier not found")
    return cashier_out(user)


class PasswordChange(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/cashiers/password")
def change_cashier_password(body: PasswordChange, db: Db, client: Client) -> dict:
    """A cashier changes their own password at a till. The current one is checked with the usual
    lockout, so a till left logged in can't be used to take the account over."""
    user = auth_svc.authenticate(db, body.username, body.current_password)
    if "pos.sell" not in permissions_for(user.role):
        raise DomainError(403, "Only cashier accounts change their password at the POS.")
    if body.new_password == body.current_password:
        raise DomainError(422, "Pick a password different from the current one.")
    user.password_hash = auth_svc.hash_password(body.new_password)
    log(db, None, "user", user.id, "password", f"{user.username} changed their password at {client.name}")
    db.commit()
    return cashier_out(user)


@router.post("/supervisors/verify")
def verify_supervisor(body: CashierLogin, db: Db, _: Client) -> dict:
    """A manager approves something at a till (a big discount, a void, a refund) with their own
    ERP login. Same lockout as a normal login; the role must allow approving."""
    user = auth_svc.authenticate(db, body.username, body.password)
    if "pos.approve" not in permissions_for(user.role):
        raise DomainError(403, f"{user.full_name} can't approve at the till. Ask a manager.")
    db.commit()
    return {"username": user.username, "full_name": user.full_name}


@router.get("/warehouses")
def warehouses(db: Db, _: Client, params: Params) -> dict:
    return paginate(db, select(Warehouse).where(Warehouse.active), params,
                    lambda w: {"id": w.public_id, "code": w.code, "name": w.name, "city": w.city},
                    default_sort=[Warehouse.id])


@router.get("/products")
def products(db: Db, _: Client, params: Params) -> dict:
    return paginate(db, select(Product).options(selectinload(Product.category)), params,
                    lambda p: {"id": p.public_id, "sku": p.sku, "name": p.name, "barcode": p.barcode, "unit": p.unit,
                               "price": p.sale_price, "active": p.active, "updated_at": p.updated_at,
                               "category": p.category.name if p.category else None, "brand": p.brand},
                    default_sort=[Product.id])


def customer_out(c: Customer) -> dict:
    # discount_pct: the group discount the ERP applies to a line sent without its own.
    return {"id": c.public_id, "code": c.code, "name": c.name, "phone": c.phone, "email": c.email,
            "group": c.group.name if c.group else None, "discount_pct": c.group.discount_pct if c.group else 0,
            "points": c.loyalty_points}


@router.get("/customers")
def customers(db: Db, _: Client, params: Params) -> dict:
    stmt = select(Customer).options(selectinload(Customer.group)).where(Customer.active)
    return paginate(db, stmt, params, customer_out, default_sort=[Customer.id])


@router.get("/customers/{customer_id}")
def get_customer(customer_id: uuid.UUID, db: Db, _: Client) -> dict:
    """One customer, e.g. for an up-to-date points balance before they spend points."""
    customer = db.scalar(select(Customer).filter_by(public_id=customer_id))
    if customer is None:
        raise HTTPException(404, "customer not found")
    return customer_out(customer)


class NewCustomer(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    phone: str | None = Field(None, max_length=40)
    email: EmailStr | None = None


@router.post("/customers", status_code=201)
def create_customer(body: NewCustomer, db: Db, client: Client) -> dict:
    """A customer signed up at a till. No group, so no discount, until someone in the ERP assigns one."""
    customer = Customer(code=next_number(db, "C", today()), name=body.name.strip(), phone=body.phone,
                        email=body.email)
    db.add(customer)
    db.flush()
    log(db, None, "customer", customer.id, "created", f"Customer {customer.name} created by {client.name}")
    db.commit()
    return customer_out(customer)


@router.get("/warehouses/{warehouse_id}/stock")
def stock(warehouse_id: uuid.UUID, db: Db, _: Client, params: Params) -> dict:
    warehouse = db.scalar(select(Warehouse).filter_by(public_id=warehouse_id))
    if warehouse is None:
        raise HTTPException(404, "warehouse not found")
    stmt = select(StockLevel).options(selectinload(StockLevel.product)).filter_by(warehouse_id=warehouse.id)
    return paginate(db, stmt, params, lambda s: {"product_id": s.product.public_id, "on_hand": s.on_hand},
                    default_sort=[StockLevel.id])


class ImportLine(BaseModel):
    product_id: uuid.UUID
    qty: int = Field(gt=0)
    unit_price: int | None = Field(None, ge=0)
    discount_pct: int | None = Field(None, ge=0, le=100)  # None: the customer group's discount


class ImportPayment(BaseModel):
    method: str
    amount: int = Field(gt=0)
    reference: str | None = Field(None, max_length=60)


class ImportOrder(BaseModel):
    external_id: str = Field(min_length=1, max_length=64)
    customer_id: uuid.UUID
    warehouse_id: uuid.UUID
    order_date: date | None = None
    reference: str | None = Field(None, max_length=60)
    lines: list[ImportLine] = Field(min_length=1, max_length=200)
    # A sale paid at a till: must add up to the order total. The goods leave the warehouse now.
    # A "points" payment spends the customer's loyalty points at their rupiah value.
    payments: list[ImportPayment] | None = Field(None, min_length=1, max_length=10)
    # A paid sale earns the customer loyalty points on what was not paid with points.
    earn_points: bool = False


def imported_out(db, o: SalesOrder) -> dict:
    invoice = db.scalar(select(Invoice).filter_by(sales_order_id=o.id).order_by(Invoice.id.desc()).limit(1))
    return {"number": o.number, "external_id": o.external_id, "status": o.status, "total": o.total,
            "invoice_number": invoice.number if invoice else None,
            "invoice_status": invoice.status if invoice else None,
            "points_earned": o.points_earned, "points_balance": o.customer.loyalty_points}


@router.post("/sales-orders", status_code=201)
def import_sales_order(body: ImportOrder, response: Response, db: Db, _: Client) -> dict:
    """Create and confirm a sales order; with `payments`, also ship, invoice and settle it.
    Sending the same external_id again returns the first order (200)."""
    existing = db.scalar(select(SalesOrder).filter_by(external_id=body.external_id))
    if existing is not None:
        response.status_code = 200
        return imported_out(db, existing)
    customer = db.scalar(select(Customer).filter_by(public_id=body.customer_id))
    warehouse = db.scalar(select(Warehouse).filter_by(public_id=body.warehouse_id))
    product_ids = {p.public_id: p.id for p in db.scalars(
        select(Product).where(Product.public_id.in_([li.product_id for li in body.lines])))}
    if customer is None or warehouse is None:
        raise DomainError(422, "Unknown customer or warehouse.")
    if missing := {li.product_id for li in body.lines} - product_ids.keys():
        raise DomainError(422, f"Unknown products: {sorted(map(str, missing))}")
    data = sales_svc.SalesOrderIn(
        customer_id=customer.id, warehouse_id=warehouse.id, order_date=body.order_date or today(),
        customer_ref=body.reference,
        lines=[sales_svc.SalesLineIn(product_ids[li.product_id], li.qty, li.unit_price, li.discount_pct)
               for li in body.lines])
    try:
        order = sales_svc.save_order(db, None, data, external_id=body.external_id)
        if body.payments is None:
            sales_svc.confirm(db, None, order)
        else:
            _settle_on_the_spot(db, order, body.payments, body.earn_points)
        db.commit()
    except IntegrityError:
        # The same order raced in on another request; answer with the one that won.
        db.rollback()
        response.status_code = 200
        return imported_out(db, db.scalar(select(SalesOrder).filter_by(external_id=body.external_id)))
    except DomainError:
        db.rollback()  # nothing of a refused sale stays behind, not even its order number
        raise
    return imported_out(db, order)


def _settle_on_the_spot(db, order: SalesOrder, payments: list[ImportPayment], earn_points: bool = False) -> None:
    """Confirm, ship everything, invoice and take the payments: a sale handed over at a counter."""
    paid = sum(p.amount for p in payments)
    if paid != order.total:
        raise DomainError(422, f"Payments add up to {rupiah(paid)}, the order total is {rupiah(order.total)}.")
    settings = all_settings(db)
    customer = order.customer
    by_points = sum(p.amount for p in payments if p.method == "points")
    if by_points:
        value = settings["loyalty_point_value"]
        if value <= 0 or by_points % value:
            raise DomainError(422, "Points must be spent in whole points.")
        if by_points // value > customer.loyalty_points:
            raise DomainError(409, f"{customer.name} has {customer.loyalty_points} points, "
                                   f"{by_points // value} were spent.")
        customer.loyalty_points -= by_points // value
    if earn_points and settings["loyalty_earn_per"] > 0:
        order.points_earned = (order.total - by_points) // settings["loyalty_earn_per"]
        customer.loyalty_points += order.points_earned
    sales_svc.confirm(db, None, order, check_credit=False)  # paid now: no credit is extended
    sales_svc.deliver(db, None, order, {li.id: li.qty for li in order.lines}, order.order_date)
    invoice = sales_svc.create_invoice(db, None, order, order.order_date)
    for p in payments:
        finance_svc.register_payment(db, None, invoice, p.amount, order.order_date, p.method, p.reference)


@router.get("/sales-orders")
def find_sales_orders(db: Db, _: Client, params: Params, external_id: str | None = None) -> dict:
    stmt = select(SalesOrder).where(SalesOrder.source == "api")
    if external_id:
        stmt = stmt.where(SalesOrder.external_id == external_id)
    return paginate(db, stmt, params, lambda o: imported_out(db, o), default_sort=[SalesOrder.id.desc()])


# ---------------------------------------------------------------- returns


class ReturnLine(BaseModel):
    product_id: uuid.UUID
    qty: int = Field(gt=0)
    # Which line of the order, when a product is on it twice (e.g. some units free with a promotion).
    unit_price: int | None = Field(None, ge=0)
    discount_pct: int | None = Field(None, ge=0, le=100)


class ImportReturn(BaseModel):
    external_id: str = Field(min_length=1, max_length=64)
    order_external_id: str = Field(min_length=1, max_length=64)
    return_date: date | None = None
    reason: str | None = Field(None, max_length=200)
    lines: list[ReturnLine] = Field(min_length=1, max_length=200)
    refunds: list[ImportPayment] = Field(min_length=1, max_length=10)


def return_out(r: SalesReturn) -> dict:
    return {"number": r.number, "external_id": r.external_id, "order_number": r.order.number, "total": r.total,
            "points_reversed": r.points_reversed, "points_balance": r.order.customer.loyalty_points}


def _order_lines_for(order: SalesOrder, lines: list[ReturnLine], product_ids: dict) -> list[sales_svc.ReturnLineIn]:
    """Spread each returned product over the order lines it was sold on, matching price and discount
    when given, so a return finds the right line even when a product is on the order twice."""
    left = {li.id: li.qty_delivered - li.qty_returned for li in order.lines}
    out = []
    for line in lines:
        product_id = product_ids.get(line.product_id)
        candidates = [li for li in order.lines if li.product_id == product_id
                      and (line.unit_price is None or li.unit_price == line.unit_price)
                      and (line.discount_pct is None or li.discount_pct == line.discount_pct)]
        qty = line.qty
        for li in candidates:
            take = min(qty, left[li.id])
            if take:
                out.append(sales_svc.ReturnLineIn(li.id, take))
                left[li.id] -= take
                qty -= take
        if qty:
            raise DomainError(422, f"{order.number}: only {line.qty - qty} of product {line.product_id} can still "
                                   f"come back, {line.qty} asked.")
    return out


@router.post("/sales-returns", status_code=201)
def import_sales_return(body: ImportReturn, response: Response, db: Db, _: Client) -> dict:
    """Goods brought back to a till: stock goes back in and the refund is booked. Sending the same
    external_id again returns the first return (200)."""
    existing = db.scalar(select(SalesReturn).filter_by(external_id=body.external_id))
    if existing is not None:
        response.status_code = 200
        return return_out(existing)
    order = db.scalar(select(SalesOrder).filter_by(external_id=body.order_external_id)
                      .options(selectinload(SalesOrder.lines).selectinload(SalesOrderLine.product)))
    if order is None:
        raise DomainError(404, f"No sales order with external id {body.order_external_id}.")
    product_ids = {p.public_id: p.id for p in db.scalars(
        select(Product).where(Product.public_id.in_([li.product_id for li in body.lines])))}
    try:
        ret = sales_svc.return_goods(
            db, None, order, _order_lines_for(order, body.lines, product_ids), body.return_date or today(),
            [sales_svc.RefundIn(r.method, r.amount, r.reference) for r in body.refunds], body.reason,
            external_id=body.external_id, point_value=all_settings(db)["loyalty_point_value"])
        db.commit()
    except IntegrityError:
        db.rollback()
        response.status_code = 200
        return return_out(db.scalar(select(SalesReturn).filter_by(external_id=body.external_id)))
    except DomainError:
        db.rollback()
        raise
    return return_out(ret)


# ---------------------------------------------------------------- promotions


@router.get("/promotions")
def promotions(db: Db, _: Client, params: Params) -> dict:
    """Running and upcoming promotions. Ended or switched-off ones drop out, so a till that mirrors
    this list stops applying them."""
    stmt = current_promotions(db, today()).options(selectinload(Promotion.product), selectinload(Promotion.category),
                                                  selectinload(Promotion.warehouse))
    return paginate(db, stmt, params, lambda p: {
        "id": p.public_id, "name": p.name, "kind": p.kind, "value": p.value, "buy_qty": p.buy_qty,
        "get_qty": p.get_qty, "code": p.code, "min_spend": p.min_spend, "starts_on": p.starts_on, "ends_on": p.ends_on,
        "product_id": p.product.public_id if p.product else None, "category": p.category.name if p.category else None,
        "warehouse_id": p.warehouse.public_id if p.warehouse else None,
    }, default_sort=[Promotion.id])


# ---------------------------------------------------------------- stock requests


class RequestLine(BaseModel):
    product_id: uuid.UUID
    qty: int = Field(gt=0, le=100_000)


class StockRequest(BaseModel):
    warehouse_id: uuid.UUID  # the store that needs the goods
    lines: list[RequestLine] = Field(min_length=1, max_length=100)
    requested_by: str = Field(min_length=1, max_length=120)
    note: str | None = Field(None, max_length=200)


@router.post("/stock-requests", status_code=201)
def request_stock(body: StockRequest, db: Db, client: Client) -> dict:
    """A store asks for goods. It becomes a draft transfer from the warehouse holding the most of
    them; the warehouse team checks it, changes it if needed, and validates it in the ERP."""
    dest = db.scalar(select(Warehouse).filter_by(public_id=body.warehouse_id))
    if dest is None or not dest.active:
        raise DomainError(422, "Unknown store.")
    products = {p.public_id: p for p in db.scalars(
        select(Product).where(Product.public_id.in_([li.product_id for li in body.lines])))}
    if missing := {li.product_id for li in body.lines} - products.keys():
        raise DomainError(422, f"Unknown products: {sorted(map(str, missing))}")
    held: dict[int, int] = {}
    for warehouse_id, qty in db.execute(
            select(StockLevel.warehouse_id, StockLevel.on_hand).join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
            .where(StockLevel.product_id.in_([p.id for p in products.values()]), StockLevel.warehouse_id != dest.id,
                   Warehouse.active)):
        held[warehouse_id] = held.get(warehouse_id, 0) + qty
    if not held or max(held.values()) <= 0:
        raise DomainError(409, "No other warehouse has any of these in stock.")
    source = max(held, key=lambda w: (held[w], -w))
    note = f"Requested at the POS by {body.requested_by} ({client.name})" + (f": {body.note}" if body.note else "")
    transfer = inventory_svc.create_transfer(
        db, None, source, dest.id, today(),
        [inventory_svc.QtyLine(products[li.product_id].id, li.qty) for li in body.lines], note[:500])
    db.commit()
    return {"number": transfer.number, "status": transfer.status, "from": transfer.from_warehouse.name,
            "to": transfer.to_warehouse.name, "units": sum(li.qty for li in transfer.lines)}
