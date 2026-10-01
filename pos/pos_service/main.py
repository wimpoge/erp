"""POS API used by the till (Next.js).

Every endpoint needs a logged-in staff member. Cashiers only see and sell in their own
store; admins can work in every store and run the ERP sync, the push queue and staff.
"""

from datetime import UTC, datetime
from typing import Annotated, Literal

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from .auth import (
    COOKIE_NAME,
    Admin,
    CurrentUser,
    LoginError,
    authenticate,
    check_location,
    end_session,
    hash_password,
    start_session,
)
from .config import Settings, get_settings
from .db import get_db, make_session_factory
from .erp_client import ErpClient
from .models import (
    Customer,
    Location,
    Order,
    OrderLine,
    Payment,
    Product,
    ProductStock,
    SyncEvent,
    SyncRun,
    SyncState,
    User,
    utcnow,
)
from .orders import OrderError, OrderIn, create_order, push_due, push_order, push_order_by_id
from .sync import run_sync


def get_erp(request: Request) -> ErpClient:
    return request.app.state.erp


Db = Annotated[Session, Depends(get_db)]
Erp = Annotated[ErpClient, Depends(get_erp)]


# ---------------------------------------------------------------- serializers


def location_out(loc: Location) -> dict:
    return {
        "id": loc.id, "code": loc.code, "name": loc.name, "city": loc.city,
        "registers": [{"id": r.id, "code": r.code, "name": r.name} for r in loc.registers if r.active],
    }


def user_out(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role, "active": u.active,
        "location": location_out(u.location) if u.location else None,
        "last_login_at": u.last_login_at,
        "locked": bool(u.locked_until and u.locked_until > utcnow()),
    }


def customer_out(c: Customer) -> dict:
    return {
        "id": c.id, "code": c.code, "name": c.name, "phone": c.phone, "email": c.email,
        "group": c.group.name if c.group else None,
        "discount_rate": c.group.discount_rate if c.group and c.group.active else 0,
    }


def order_out(o: Order, detail: bool = False) -> dict:
    out = {
        "id": o.id, "number": o.number, "external_id": o.external_id, "created_at": o.created_at,
        "location": o.location.code, "location_name": o.location.name,
        "register": o.register.name if o.register else None,
        "customer": o.customer.name if o.customer else None,
        "cashier": o.cashier.full_name if o.cashier else None,
        "subtotal": o.subtotal, "discount": o.discount, "total": o.total, "paid": o.paid, "change": o.change,
        "items": sum(li.qty for li in o.lines),
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
        selectinload(Order.cashier), selectinload(Order.lines).selectinload(OrderLine.product),
        selectinload(Order.payments), selectinload(Order.push_log),
    )


def _get_order(db: Session, user: User, order_id: int) -> Order:
    order = db.scalar(_order_query().where(Order.id == order_id))
    if order is None or (user.role != "admin" and order.location_id != user.location_id):
        raise HTTPException(404, "Sale not found.")
    return order


# ---------------------------------------------------------------- request bodies


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=6, max_length=200)
    role: Literal["cashier", "admin"] = "cashier"
    location_id: int | None = None


class UserPatch(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=120)
    password: str | None = Field(None, min_length=6, max_length=200)
    role: Literal["cashier", "admin"] | None = None
    location_id: int | None = None
    active: bool | None = None
    unlock: bool | None = None


def _check_user_location(db: Session, role: str, location_id: int | None) -> None:
    if location_id is not None and db.get(Location, location_id) is None:
        raise HTTPException(422, "Unknown store.")
    if role == "cashier" and location_id is None:
        raise HTTPException(422, "A cashier needs a store.")


# ---------------------------------------------------------------- app


def create_app(
    session_factory: sessionmaker | None = None,
    erp: ErpClient | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="POS", version="0.2.0")
    app.state.settings = settings
    app.state.session_factory = session_factory or make_session_factory(settings.database_url)
    app.state.erp = erp or ErpClient(
        httpx.Client(base_url=settings.erp_base_url, timeout=10),
        settings.erp_client_id, settings.erp_client_secret, settings.erp_app_code,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    # ------------------------------------------------------------ auth

    @app.post("/api/auth/login")
    def login(body: LoginIn, response: Response, db: Db) -> dict:
        try:
            user = authenticate(db, body.username, body.password)
        except LoginError as exc:
            raise HTTPException(exc.status_code, exc.message) from None
        token, max_age = start_session(db, user, settings.session_hours)
        response.set_cookie(
            COOKIE_NAME, token, max_age=max_age, httponly=True, samesite="lax",
            secure=settings.cookie_secure, path="/",
        )
        return user_out(user)

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response, db: Db) -> None:
        end_session(db, request.cookies.get(COOKIE_NAME))
        response.delete_cookie(COOKIE_NAME, path="/")

    @app.get("/api/auth/me")
    def me(user: CurrentUser) -> dict:
        return user_out(user)

    # ------------------------------------------------------------ catalogue

    @app.get("/api/locations")
    def list_locations(db: Db, user: CurrentUser) -> list[dict]:
        stmt = select(Location).options(selectinload(Location.registers)).filter_by(active=True).order_by(Location.code)
        if user.role != "admin":
            stmt = stmt.filter_by(id=user.location_id)
        return [location_out(loc) for loc in db.scalars(stmt)]

    @app.get("/api/products")
    def list_products(
        db: Db,
        user: CurrentUser,
        location_id: int,
        q: str | None = None,
        category: str | None = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    ) -> list[dict]:
        check_location(user, location_id)
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
    def list_customers(
        db: Db, _: CurrentUser, q: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 20
    ) -> list[dict]:
        stmt = select(Customer).options(selectinload(Customer.group)).where(Customer.active).order_by(Customer.name)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like), Customer.code.ilike(like)))
        return [customer_out(c) for c in db.scalars(stmt.limit(limit))]

    # ------------------------------------------------------------ sales

    @app.post("/api/orders", status_code=201)
    def place_order(body: OrderIn, request: Request, background: BackgroundTasks, db: Db, user: CurrentUser) -> dict:
        check_location(user, body.location_id)
        try:
            order = create_order(db, body, cashier=user)
        except OrderError as exc:
            raise HTTPException(exc.status_code, exc.message) from None
        # Respond to the till straight away; the ERP push happens after the response.
        background.add_task(
            push_order_by_id, request.app.state.session_factory, request.app.state.erp,
            order.id, settings.push_max_attempts,
        )
        return order_out(db.scalar(_order_query().where(Order.id == order.id)), detail=True)

    def _orders_filter(stmt, user: User, location_id: int | None, since: datetime | None):
        if user.role != "admin":
            location_id = user.location_id
        if location_id is not None:
            stmt = stmt.where(Order.location_id == location_id)
        if since is not None:
            # The till sends the start of its local day with an offset; the database keeps naive UTC.
            if since.tzinfo is not None:
                since = since.astimezone(UTC).replace(tzinfo=None)
            stmt = stmt.where(Order.created_at >= since)
        return stmt

    @app.get("/api/orders")
    def list_orders(
        db: Db,
        user: CurrentUser,
        location_id: int | None = None,
        push_status: str | None = None,
        since: datetime | None = None,
        q: str | None = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[dict]:
        stmt = _orders_filter(_order_query(), user, location_id, since).order_by(Order.id.desc()).limit(limit)
        if push_status:
            stmt = stmt.where(Order.push_status == push_status)
        if q:
            like = f"%{q}%"
            stmt = stmt.outerjoin(Customer, Order.customer_id == Customer.id).where(
                or_(Order.number.ilike(like), Customer.name.ilike(like))
            )
        return [order_out(o) for o in db.scalars(stmt)]

    @app.get("/api/orders/summary")
    def orders_summary(
        db: Db, user: CurrentUser, location_id: int | None = None, since: datetime | None = None
    ) -> dict:
        orders = _orders_filter(select(Order.id, Order.total), user, location_id, since).subquery()
        count, revenue = db.execute(select(func.count(orders.c.id), func.coalesce(func.sum(orders.c.total), 0))).one()
        # What should be in each drawer: payments minus the change handed back in cash.
        by_method = dict(db.execute(
            select(Payment.method, func.sum(Payment.amount)).where(Payment.order_id.in_(select(orders.c.id)))
            .group_by(Payment.method)
        ).all())
        change = db.scalar(select(func.coalesce(func.sum(Order.change), 0)).where(Order.id.in_(select(orders.c.id))))
        if "cash" in by_method:
            by_method["cash"] -= change
        return {"count": count, "revenue": revenue, "by_method": by_method}

    @app.get("/api/orders/{order_id}")
    def get_order(order_id: int, db: Db, user: CurrentUser) -> dict:
        return order_out(_get_order(db, user, order_id), detail=True)

    @app.post("/api/orders/{order_id}/push")
    def push_one(order_id: int, db: Db, erp: Erp, admin: Admin) -> dict:
        """Manual push, also for orders that gave up retrying."""
        order = _get_order(db, admin, order_id)
        if order.push_status == "failed":
            order.push_status = "pending"
            order.push_attempts = 0
        push_order(db, erp, order, settings.push_max_attempts)
        return order_out(db.scalar(_order_query().where(Order.id == order_id)), detail=True)

    @app.post("/api/orders/push-pending")
    def push_pending(db: Db, erp: Erp, _: Admin) -> dict:
        return push_due(db, erp, settings.push_max_attempts)

    # ------------------------------------------------------------ ERP sync (admin)

    @app.post("/api/sync")
    def sync_now(db: Db, erp: Erp, _: Admin) -> dict:
        run = run_sync(db, erp)
        return {"id": run.id, "status": run.status, "started_at": run.started_at,
                "finished_at": run.finished_at, "summary": run.summary}

    @app.get("/api/sync/runs")
    def list_runs(db: Db, _: Admin, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[dict]:
        runs = db.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(limit))
        return [{"id": r.id, "status": r.status, "started_at": r.started_at, "finished_at": r.finished_at,
                 "summary": r.summary} for r in runs]

    @app.get("/api/sync/runs/{run_id}/events")
    def list_events(
        run_id: int, db: Db, _: Admin, action: str | None = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    ) -> list[dict]:
        stmt = select(SyncEvent).filter_by(run_id=run_id).order_by(SyncEvent.id).limit(limit)
        if action:
            stmt = stmt.filter_by(action=action)
        return [{"id": e.id, "table": e.table, "action": e.action, "erp_public_id": e.erp_public_id,
                 "message": e.message, "at": e.created_at} for e in db.scalars(stmt)]

    @app.get("/api/sync/state")
    def sync_state(db: Db, _: Admin) -> list[dict]:
        return [{"key": s.key, "last_status": s.last_status, "last_synced_at": s.last_synced_at, "rows": s.rows}
                for s in db.scalars(select(SyncState).order_by(SyncState.key))]

    # ------------------------------------------------------------ staff (admin)

    @app.get("/api/users")
    def list_users(db: Db, _: Admin) -> list[dict]:
        stmt = select(User).options(selectinload(User.location).selectinload(Location.registers)).order_by(User.username)
        return [user_out(u) for u in db.scalars(stmt)]

    @app.post("/api/users", status_code=201)
    def create_user(body: UserIn, db: Db, _: Admin) -> dict:
        username = body.username.lower()
        if db.scalar(select(User).filter_by(username=username)) is not None:
            raise HTTPException(409, "That username is taken.")
        _check_user_location(db, body.role, body.location_id)
        user = User(username=username, full_name=body.full_name.strip(), password_hash=hash_password(body.password),
                    role=body.role, location_id=body.location_id)
        db.add(user)
        db.commit()
        return user_out(user)

    @app.patch("/api/users/{user_id}")
    def update_user(user_id: int, body: UserPatch, db: Db, admin: Admin) -> dict:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(404, "User not found.")
        changes = body.model_dump(exclude_unset=True)
        if user.id == admin.id and (changes.get("active") is False or changes.get("role") == "cashier"):
            raise HTTPException(422, "You cannot deactivate or demote yourself.")
        role = changes.get("role", user.role)
        location_id = changes["location_id"] if "location_id" in changes else user.location_id
        _check_user_location(db, role, location_id)
        for field in ("full_name", "role", "active"):
            if field in changes:
                setattr(user, field, changes[field])
        user.location_id = location_id
        if body.password:
            user.password_hash = hash_password(body.password)
        if body.unlock or body.password:
            user.locked_until, user.failed_logins = None, 0
        db.commit()
        return user_out(user)

    return app
