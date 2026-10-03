"""Integration API for outside systems (a POS, a web shop).

Client-credentials tokens, paginated lists that expose only public UUIDs, and a sales
order import that is idempotent on the caller's `external_id`, so a retried request
never creates a second order.
"""

import hmac
import secrets
import uuid
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ..models import ApiClient, ApiToken, Customer, Product, SalesOrder, StockLevel, Warehouse, today, utcnow
from ..services import sales as sales_svc
from ..services.auth import sha256
from ..services.common import DomainError
from .deps import Db, Params, paginate

router = APIRouter(prefix="/api/integration/v1", tags=["integration API"])


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


@router.get("/warehouses")
def warehouses(db: Db, _: Client, params: Params) -> dict:
    return paginate(db, select(Warehouse).where(Warehouse.active), params,
                    lambda w: {"id": w.public_id, "code": w.code, "name": w.name, "city": w.city},
                    default_sort=[Warehouse.id])


@router.get("/products")
def products(db: Db, _: Client, params: Params) -> dict:
    return paginate(db, select(Product), params,
                    lambda p: {"id": p.public_id, "sku": p.sku, "name": p.name, "barcode": p.barcode, "unit": p.unit,
                               "price": p.sale_price, "active": p.active, "updated_at": p.updated_at},
                    default_sort=[Product.id])


@router.get("/customers")
def customers(db: Db, _: Client, params: Params) -> dict:
    return paginate(db, select(Customer).where(Customer.active), params,
                    lambda c: {"id": c.public_id, "code": c.code, "name": c.name, "phone": c.phone, "email": c.email},
                    default_sort=[Customer.id])


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


class ImportOrder(BaseModel):
    external_id: str = Field(min_length=1, max_length=64)
    customer_id: uuid.UUID
    warehouse_id: uuid.UUID
    order_date: date | None = None
    reference: str | None = Field(None, max_length=60)
    lines: list[ImportLine] = Field(min_length=1, max_length=200)


def imported_out(o: SalesOrder) -> dict:
    return {"number": o.number, "external_id": o.external_id, "status": o.status, "total": o.total}


@router.post("/sales-orders", status_code=201)
def import_sales_order(body: ImportOrder, response: Response, db: Db, _: Client) -> dict:
    """Create and confirm a sales order. Sending the same external_id again returns the first order (200)."""
    existing = db.scalar(select(SalesOrder).filter_by(external_id=body.external_id))
    if existing is not None:
        response.status_code = 200
        return imported_out(existing)
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
        lines=[sales_svc.SalesLineIn(product_ids[li.product_id], li.qty, li.unit_price) for li in body.lines])
    try:
        order = sales_svc.save_order(db, None, data, external_id=body.external_id)
        sales_svc.confirm(db, None, order)
        db.commit()
    except IntegrityError:
        # The same order raced in on another request; answer with the one that won.
        db.rollback()
        response.status_code = 200
        return imported_out(db.scalar(select(SalesOrder).filter_by(external_id=body.external_id)))
    return imported_out(order)


@router.get("/sales-orders")
def find_sales_orders(db: Db, _: Client, params: Params, external_id: str | None = None) -> dict:
    stmt = select(SalesOrder).where(SalesOrder.source == "api")
    if external_id:
        stmt = stmt.where(SalesOrder.external_id == external_id)
    return paginate(db, stmt, params, imported_out, default_sort=[SalesOrder.id.desc()])
