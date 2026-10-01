"""POS API used by the till (Next.js) and by staff to run syncs and retry pushes."""

from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from .config import Settings, get_settings
from .db import make_session_factory
from .erp_client import ErpClient
from .models import (
    Customer,
    Location,
    Order,
    OrderLine,
    Product,
    ProductStock,
    SyncEvent,
    SyncRun,
    SyncState,
)
from .orders import OrderError, OrderIn, create_order, push_due, push_order, push_order_by_id
from .sync import run_sync


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as db:
        yield db


def get_erp(request: Request) -> ErpClient:
    return request.app.state.erp


Db = Annotated[Session, Depends(get_db)]
Erp = Annotated[ErpClient, Depends(get_erp)]


def location_out(loc: Location) -> dict:
    return {
        "id": loc.id, "code": loc.code, "name": loc.name, "city": loc.city,
        "registers": [{"id": r.id, "code": r.code, "name": r.name} for r in loc.registers if r.active],
    }


def customer_out(c: Customer) -> dict:
    return {
        "id": c.id, "code": c.code, "name": c.name, "phone": c.phone, "email": c.email,
        "group": c.group.name if c.group else None,
        "discount_rate": c.group.discount_rate if c.group else 0,
    }


def order_out(o: Order, detail: bool = False) -> dict:
    out = {
        "id": o.id, "number": o.number, "external_id": o.external_id, "created_at": o.created_at,
        "location": o.location.code, "register": o.register.code if o.register else None,
        "customer": o.customer.name if o.customer else None,
        "subtotal": o.subtotal, "discount": o.discount, "total": o.total, "paid": o.paid, "change": o.change,
        "push_status": o.push_status, "push_attempts": o.push_attempts, "next_push_at": o.next_push_at,
        "last_push_error": o.last_push_error, "erp_number": o.erp_number,
    }
    if detail:
        out["lines"] = [
            {"product_id": li.product_id, "sku": li.product.sku, "name": li.product.name,
             "qty": li.qty, "unit_price": li.unit_price, "line_total": li.line_total}
            for li in o.lines
        ]
        out["payments"] = [{"method": p.method, "amount": p.amount} for p in o.payments]
        out["push_log"] = [
            {"attempt": a.attempt, "ok": a.ok, "status_code": a.status_code, "error": a.error, "at": a.created_at}
            for a in o.push_log
        ]
    return out


def _order_query():
    return select(Order).options(
        selectinload(Order.location), selectinload(Order.register), selectinload(Order.customer),
        selectinload(Order.lines).selectinload(OrderLine.product), selectinload(Order.payments),
        selectinload(Order.push_log),
    )


def create_app(
    session_factory: sessionmaker | None = None,
    erp: ErpClient | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="POS", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = session_factory or make_session_factory(settings.database_url)
    app.state.erp = erp or ErpClient(
        httpx.Client(base_url=settings.erp_base_url, timeout=10),
        settings.erp_client_id, settings.erp_client_secret, settings.erp_app_code,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"]
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    # ------------------------------------------------------------ catalogue

    @app.get("/api/locations")
    def list_locations(db: Db) -> list[dict]:
        stmt = select(Location).options(selectinload(Location.registers)).filter_by(active=True).order_by(Location.code)
        return [location_out(loc) for loc in db.scalars(stmt)]

    @app.get("/api/products")
    def list_products(
        db: Db,
        location_id: int,
        q: str | None = None,
        category: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
    ) -> list[dict]:
        stmt = (
            select(Product, ProductStock.on_hand)
            .outerjoin(ProductStock, (ProductStock.product_id == Product.id) & (ProductStock.location_id == location_id))
            .where(Product.active)
            .order_by(Product.category, Product.name)
            .limit(limit)
        )
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(Product.name.ilike(like), Product.sku.ilike(like), Product.barcode == q))
        if category:
            stmt = stmt.where(Product.category == category)
        return [
            {"id": p.id, "sku": p.sku, "name": p.name, "barcode": p.barcode, "brand": p.brand,
             "category": p.category, "price": p.price, "on_hand": on_hand or 0}
            for p, on_hand in db.execute(stmt)
        ]

    @app.get("/api/customers")
    def list_customers(db: Db, q: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[dict]:
        stmt = select(Customer).options(selectinload(Customer.group)).where(Customer.active).order_by(Customer.name)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like), Customer.code.ilike(like)))
        return [customer_out(c) for c in db.scalars(stmt.limit(limit))]

    # ------------------------------------------------------------ orders

    @app.post("/api/orders", status_code=201)
    def place_order(body: OrderIn, request: Request, background: BackgroundTasks, db: Db) -> dict:
        try:
            order = create_order(db, body)
        except OrderError as exc:
            raise HTTPException(exc.status_code, exc.message) from None
        # Respond to the till straight away; the ERP push happens after the response.
        background.add_task(
            push_order_by_id, request.app.state.session_factory, request.app.state.erp,
            order.id, request.app.state.settings.push_max_attempts,
        )
        return order_out(db.scalar(_order_query().where(Order.id == order.id)), detail=True)

    @app.get("/api/orders")
    def list_orders(
        db: Db,
        location_id: int | None = None,
        push_status: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> list[dict]:
        stmt = _order_query().order_by(Order.id.desc()).limit(limit)
        if location_id is not None:
            stmt = stmt.where(Order.location_id == location_id)
        if push_status:
            stmt = stmt.where(Order.push_status == push_status)
        return [order_out(o) for o in db.scalars(stmt)]

    @app.get("/api/orders/{order_id}")
    def get_order(order_id: int, db: Db) -> dict:
        order = db.scalar(_order_query().where(Order.id == order_id))
        if order is None:
            raise HTTPException(404, "order not found")
        return order_out(order, detail=True)

    @app.post("/api/orders/{order_id}/push")
    def push_one(order_id: int, db: Db, erp: Erp, request: Request) -> dict:
        """Manual push, also for orders that gave up retrying."""
        order = db.scalar(_order_query().where(Order.id == order_id))
        if order is None:
            raise HTTPException(404, "order not found")
        if order.push_status == "failed":
            order.push_status = "pending"
            order.push_attempts = 0
        push_order(db, erp, order, request.app.state.settings.push_max_attempts)
        return order_out(db.scalar(_order_query().where(Order.id == order_id)), detail=True)

    @app.post("/api/orders/push-pending")
    def push_pending(db: Db, erp: Erp, request: Request) -> dict:
        return push_due(db, erp, request.app.state.settings.push_max_attempts)

    # ------------------------------------------------------------ sync

    @app.post("/api/sync")
    def sync_now(db: Db, erp: Erp) -> dict:
        run = run_sync(db, erp)
        return {"id": run.id, "status": run.status, "started_at": run.started_at,
                "finished_at": run.finished_at, "summary": run.summary}

    @app.get("/api/sync/runs")
    def list_runs(db: Db, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[dict]:
        runs = db.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(limit))
        return [{"id": r.id, "status": r.status, "started_at": r.started_at, "finished_at": r.finished_at,
                 "summary": r.summary} for r in runs]

    @app.get("/api/sync/runs/{run_id}/events")
    def list_events(
        run_id: int, db: Db, action: str | None = None, limit: Annotated[int, Query(ge=1, le=1000)] = 200
    ) -> list[dict]:
        stmt = select(SyncEvent).filter_by(run_id=run_id).order_by(SyncEvent.id).limit(limit)
        if action:
            stmt = stmt.filter_by(action=action)
        return [{"id": e.id, "table": e.table, "action": e.action, "erp_public_id": e.erp_public_id,
                 "message": e.message, "at": e.created_at} for e in db.scalars(stmt)]

    @app.get("/api/sync/state")
    def sync_state(db: Db) -> list[dict]:
        return [{"key": s.key, "last_status": s.last_status, "last_synced_at": s.last_synced_at, "rows": s.rows}
                for s in db.scalars(select(SyncState).order_by(SyncState.key))]

    return app
