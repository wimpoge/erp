"""Mock ERP API.

Behaves like the kind of ERP a POS has to integrate with: client-credentials tokens,
paginated lists that expose public UUIDs only, nested child rows, and a sales-order
endpoint that is idempotent on the caller's `external_id`.
"""

import hashlib
import hmac
import random
import secrets
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import Select, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload, sessionmaker

from .config import Settings, get_settings
from .db import make_session_factory
from .models import (
    ApiClient,
    ApiToken,
    Customer,
    CustomerGroup,
    Product,
    Register,
    SalesOrder,
    SalesOrderLine,
    Stock,
    Store,
    utcnow,
)


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


# ---------------------------------------------------------------- dependencies


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as db:
        yield db


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


Db = Annotated[Session, Depends(get_db)]


def require_client(db: Db, authorization: Annotated[str | None, Header()] = None) -> ApiClient:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = db.get(ApiToken, authorization.removeprefix("Bearer "))
    if token is None or token.expires_at < utcnow():
        raise HTTPException(401, "invalid or expired token")
    return token.client


Client = Annotated[ApiClient, Depends(require_client)]


class Page:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=500)] = 100,
    ):
        self.page = page
        self.page_size = page_size

    def apply(self, db: Session, stmt: Select, serialize) -> dict:
        total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
        rows = db.scalars(stmt.offset((self.page - 1) * self.page_size).limit(self.page_size)).all()
        return {
            "items": [serialize(r) for r in rows],
            "page": self.page,
            "page_size": self.page_size,
            "total": total,
        }


Paging = Annotated[Page, Depends()]


# ---------------------------------------------------------------- serializers


def store_out(s: Store) -> dict:
    return {
        "id": s.public_id,
        "code": s.code,
        "name": s.name,
        "city": s.city,
        "active": s.active,
        "updated_at": s.updated_at,
        "registers": [
            {"id": r.public_id, "code": r.code, "name": r.name, "active": r.active} for r in s.registers
        ],
    }


def group_out(g: CustomerGroup) -> dict:
    return {"id": g.public_id, "code": g.code, "name": g.name, "discount_rate": g.discount_rate, "active": g.active}


def customer_out(c: Customer) -> dict:
    return {
        "id": c.public_id,
        "code": c.code,
        "name": c.name,
        "phone": c.phone,
        "email": c.email,
        "group_id": c.group.public_id if c.group else None,
        "active": c.active,
        "updated_at": c.updated_at,
    }


def product_out(p: Product) -> dict:
    return {
        "id": p.public_id,
        "sku": p.sku,
        "name": p.name,
        "barcode": p.barcode,
        "brand": p.brand,
        "category": p.category,
        "price": p.price,
        "active": p.active,
        "updated_at": p.updated_at,
    }


def stock_out(s: Stock) -> dict:
    return {"product_id": s.product.public_id, "on_hand": s.on_hand}


def sales_order_out(o: SalesOrder) -> dict:
    return {
        "id": o.public_id,
        "number": o.number,
        "external_id": o.external_id,
        "store_id": o.store.public_id,
        "register_id": o.register.public_id if o.register else None,
        "customer_id": o.customer.public_id if o.customer else None,
        "subtotal": o.subtotal,
        "discount": o.discount,
        "total": o.total,
        "ordered_at": o.ordered_at,
        "received_at": o.received_at,
        "lines": [
            {"product_id": li.product.public_id, "qty": li.qty, "unit_price": li.unit_price, "line_total": li.line_total}
            for li in o.lines
        ],
    }


# ---------------------------------------------------------------- request bodies


class TokenRequest(BaseModel):
    grant_type: Literal["client_credentials"] = "client_credentials"
    client_id: str
    client_secret: str
    app_code: str


class SalesOrderLineIn(BaseModel):
    product_id: uuid.UUID
    qty: int = Field(gt=0)
    unit_price: int = Field(ge=0)


class SalesOrderIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=64)
    store_id: uuid.UUID
    register_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    discount: int = Field(0, ge=0)
    ordered_at: datetime | None = None
    lines: list[SalesOrderLineIn] = Field(min_length=1)


class ProductPatch(BaseModel):
    name: str | None = None
    price: int | None = Field(None, ge=0)
    active: bool | None = None


# ---------------------------------------------------------------- app


def create_app(session_factory: sessionmaker | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Mock ERP", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = session_factory or make_session_factory(settings.database_url)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/oauth/token")
    def issue_token(body: TokenRequest, db: Db, cfg: Annotated[Settings, Depends(get_app_settings)]) -> dict:
        client = db.scalar(select(ApiClient).filter_by(client_id=body.client_id, active=True))
        if (
            client is None
            or not hmac.compare_digest(client.secret_hash, hash_secret(body.client_secret))
            or client.app_code != body.app_code
        ):
            raise HTTPException(401, "invalid client credentials")
        token = ApiToken(
            token=secrets.token_urlsafe(32),
            client_id=client.id,
            expires_at=utcnow() + timedelta(seconds=cfg.token_ttl_seconds),
        )
        db.add(token)
        db.commit()
        return {"access_token": token.token, "token_type": "bearer", "expires_in": cfg.token_ttl_seconds}

    @app.delete("/oauth/tokens", status_code=204)
    def revoke_tokens(db: Db, client: Client) -> None:
        """Revoke every token of the calling client (handy to demo the POS re-login)."""
        db.execute(delete(ApiToken).where(ApiToken.client_id == client.id))
        db.commit()

    @app.get("/api/stores")
    def list_stores(db: Db, _: Client, paging: Paging) -> dict:
        stmt = select(Store).options(selectinload(Store.registers)).order_by(Store.id)
        return paging.apply(db, stmt, store_out)

    @app.get("/api/stores/{store_id}/stock")
    def list_stock(store_id: uuid.UUID, db: Db, _: Client, paging: Paging) -> dict:
        store = db.scalar(select(Store).filter_by(public_id=store_id))
        if store is None:
            raise HTTPException(404, "store not found")
        stmt = select(Stock).options(selectinload(Stock.product)).filter_by(store_id=store.id).order_by(Stock.id)
        return paging.apply(db, stmt, stock_out)

    @app.get("/api/customer-groups")
    def list_customer_groups(db: Db, _: Client, paging: Paging) -> dict:
        return paging.apply(db, select(CustomerGroup).order_by(CustomerGroup.id), group_out)

    @app.get("/api/customers")
    def list_customers(db: Db, _: Client, paging: Paging) -> dict:
        stmt = select(Customer).options(selectinload(Customer.group)).order_by(Customer.id)
        return paging.apply(db, stmt, customer_out)

    @app.get("/api/products")
    def list_products(db: Db, _: Client, paging: Paging) -> dict:
        return paging.apply(db, select(Product).order_by(Product.id), product_out)

    @app.patch("/api/products/{product_id}")
    def patch_product(product_id: uuid.UUID, body: ProductPatch, db: Db, _: Client) -> dict:
        product = db.scalar(select(Product).filter_by(public_id=product_id))
        if product is None:
            raise HTTPException(404, "product not found")
        for field, value in body.model_dump(exclude_none=True).items():
            setattr(product, field, value)
        db.commit()
        return product_out(product)

    @app.get("/api/sales-orders")
    def list_sales_orders(db: Db, _: Client, paging: Paging, external_id: str | None = None) -> dict:
        stmt = select(SalesOrder).options(
            selectinload(SalesOrder.store),
            selectinload(SalesOrder.register),
            selectinload(SalesOrder.customer),
            selectinload(SalesOrder.lines).selectinload(SalesOrderLine.product),
        )
        if external_id is not None:
            stmt = stmt.filter_by(external_id=external_id)
        return paging.apply(db, stmt.order_by(SalesOrder.id.desc()), sales_order_out)

    @app.post("/api/sales-orders", status_code=201)
    def create_sales_order(
        body: SalesOrderIn,
        response: Response,
        db: Db,
        _: Client,
        cfg: Annotated[Settings, Depends(get_app_settings)],
    ) -> dict:
        if cfg.fail_rate and random.random() < cfg.fail_rate:
            raise HTTPException(503, "ERP temporarily unavailable")

        existing = db.scalar(select(SalesOrder).filter_by(external_id=body.external_id))
        if existing is not None:
            response.status_code = 200
            return sales_order_out(existing)

        store = db.scalar(select(Store).filter_by(public_id=body.store_id, active=True))
        if store is None:
            raise HTTPException(422, "unknown or inactive store")
        register = None
        if body.register_id is not None:
            register = db.scalar(select(Register).filter_by(public_id=body.register_id, store_id=store.id))
            if register is None:
                raise HTTPException(422, "unknown register for this store")
        customer = None
        if body.customer_id is not None:
            customer = db.scalar(select(Customer).filter_by(public_id=body.customer_id))
            if customer is None:
                raise HTTPException(422, "unknown customer")

        wanted = {line.product_id for line in body.lines}
        products = {p.public_id: p for p in db.scalars(select(Product).where(Product.public_id.in_(wanted)))}
        if missing := wanted - products.keys():
            raise HTTPException(422, f"unknown products: {sorted(map(str, missing))}")

        subtotal = sum(line.qty * line.unit_price for line in body.lines)
        if body.discount > subtotal:
            raise HTTPException(422, "discount exceeds subtotal")

        order = SalesOrder(
            external_id=body.external_id,
            store=store,
            register=register,
            customer=customer,
            subtotal=subtotal,
            discount=body.discount,
            total=subtotal - body.discount,
            ordered_at=body.ordered_at.replace(tzinfo=None) if body.ordered_at else utcnow(),
        )
        for line in body.lines:
            product = products[line.product_id]
            order.lines.append(
                SalesOrderLine(
                    product=product, qty=line.qty, unit_price=line.unit_price, line_total=line.qty * line.unit_price
                )
            )
            stock = db.scalar(select(Stock).filter_by(product_id=product.id, store_id=store.id))
            if stock is not None:
                stock.on_hand = max(0, stock.on_hand - line.qty)
        db.add(order)
        try:
            db.flush()
            order.number = f"SO-{order.received_at:%Y}-{order.id:06d}"
            db.commit()
        except IntegrityError:
            # Two pushes of the same order raced; the other one won, so answer with it.
            db.rollback()
            existing = db.scalar(select(SalesOrder).filter_by(external_id=body.external_id))
            if existing is None:
                raise
            response.status_code = 200
            return sales_order_out(existing)
        return sales_order_out(order)

    return app
