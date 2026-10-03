"""Customers, customer groups and suppliers."""

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ..models import Customer, CustomerGroup, Invoice, PurchaseOrder, SalesOrder, Supplier, today
from ..services.common import DomainError, get_or_404, log, next_number, rupiah
from ..services.sales import credit_exposure
from .deps import Db, Params, can, like, paginate
from .serializers import timeline

router = APIRouter(prefix="/api", tags=["partners"])


def _commit_unique(db, message: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DomainError(409, message) from None


def _balances(db, kind: str, ids: list[int]) -> dict[int, tuple[int, int]]:
    """Open and overdue balance per partner."""
    col = Invoice.customer_id if kind == "customer" else Invoice.supplier_id
    overdue = func.sum(func.coalesce((Invoice.total - Invoice.amount_paid), 0)).filter(Invoice.due_date < today())
    rows = db.execute(
        select(col, func.sum(Invoice.total - Invoice.amount_paid), overdue)
        .where(Invoice.kind == kind, Invoice.status == "open", col.in_(ids)).group_by(col)
    )
    return {pid: (open_ or 0, late or 0) for pid, open_, late in rows}


# ---------------------------------------------------------------- customer groups


class GroupIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=80)
    discount_pct: int = Field(0, ge=0, le=100)


@router.get("/customer-groups")
def list_groups(db: Db, _: can("sales.read")) -> list[dict]:
    counts = dict(db.execute(select(Customer.group_id, func.count()).group_by(Customer.group_id)).all())
    return [{"id": g.id, "code": g.code, "name": g.name, "discount_pct": g.discount_pct, "customers": counts.get(g.id, 0)}
            for g in db.scalars(select(CustomerGroup).order_by(CustomerGroup.name))]


@router.post("/customer-groups", status_code=201)
def create_group(body: GroupIn, db: Db, _: can("sales.write")) -> dict:
    group = CustomerGroup(**{**body.model_dump(), "code": body.code.strip().upper()})
    db.add(group)
    _commit_unique(db, "That group code is already used.")
    return {"id": group.id, "code": group.code, "name": group.name, "discount_pct": group.discount_pct, "customers": 0}


@router.put("/customer-groups/{group_id}")
def update_group(group_id: int, body: GroupIn, db: Db, _: can("sales.write")) -> dict:
    group = get_or_404(db, CustomerGroup, group_id, "Customer group")
    for field, value in body.model_dump().items():
        setattr(group, field, value)
    group.code = group.code.strip().upper()
    _commit_unique(db, "That group code is already used.")
    return {"id": group.id, "code": group.code, "name": group.name, "discount_pct": group.discount_pct}


# ---------------------------------------------------------------- customers


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=40)
    address: str | None = Field(None, max_length=250)
    city: str | None = Field(None, max_length=80)
    group_id: int | None = None
    credit_limit: int = Field(0, ge=0)
    payment_terms_days: int = Field(30, ge=0, le=365)
    active: bool = True


def customer_row(c: Customer, balance: tuple[int, int] = (0, 0)) -> dict:
    return {
        "id": c.id, "code": c.code, "name": c.name, "email": c.email, "phone": c.phone, "address": c.address,
        "city": c.city, "active": c.active, "credit_limit": c.credit_limit, "payment_terms_days": c.payment_terms_days,
        "group": {"id": c.group.id, "name": c.group.name, "discount_pct": c.group.discount_pct} if c.group else None,
        "balance": balance[0], "overdue": balance[1], "loyalty_points": c.loyalty_points,
    }


@router.get("/customers")
def list_customers(db: Db, _: can("sales.read"), params: Params, group_id: int | None = None,
                   active: bool | None = True, overdue: bool = False) -> dict:
    stmt = select(Customer).options(selectinload(Customer.group))
    if params.q:
        stmt = stmt.where(or_(Customer.name.ilike(like(params.q)), Customer.code.ilike(like(params.q)),
                              Customer.email.ilike(like(params.q)), Customer.phone.ilike(like(params.q))))
    if group_id:
        stmt = stmt.where(Customer.group_id == group_id)
    if active is not None:
        stmt = stmt.where(Customer.active == active)
    if overdue:
        stmt = stmt.where(Customer.id.in_(select(Invoice.customer_id).where(
            Invoice.kind == "customer", Invoice.status == "open", Invoice.due_date < today())))
    page = paginate(db, stmt, params, lambda c: c, sortable={"code": Customer.code, "name": Customer.name,
                                                               "city": Customer.city}, default_sort=[Customer.name])
    balances = _balances(db, "customer", [c.id for c in page["items"]])
    page["items"] = [customer_row(c, balances.get(c.id, (0, 0))) for c in page["items"]]
    return page


@router.get("/customers/{customer_id}")
def get_customer(customer_id: int, db: Db, _: can("sales.read")) -> dict:
    c = get_or_404(db, Customer, customer_id, "Customer")
    orders = db.scalars(select(SalesOrder).filter_by(customer_id=c.id).order_by(SalesOrder.id.desc()).limit(10))
    invoices = db.scalars(select(Invoice).filter_by(kind="customer", customer_id=c.id)
                          .order_by(Invoice.id.desc()).limit(10))
    revenue = db.scalar(select(func.coalesce(func.sum(Invoice.subtotal), 0)).where(
        Invoice.kind == "customer", Invoice.customer_id == c.id, Invoice.status != "cancelled"))
    return {
        **customer_row(c, _balances(db, "customer", [c.id]).get(c.id, (0, 0))),
        "credit_used": credit_exposure(db, c.id),
        "lifetime_revenue": revenue,
        "recent_orders": [{"id": o.id, "number": o.number, "order_date": o.order_date, "status": o.status,
                           "total": o.total} for o in orders],
        "recent_invoices": [{"id": i.id, "number": i.number, "issue_date": i.issue_date, "due_date": i.due_date,
                             "status": i.status, "total": i.total, "balance": i.balance} for i in invoices],
        "activity": timeline(db, "customer", c.id),
    }


@router.post("/customers", status_code=201)
def create_customer(body: CustomerIn, db: Db, user: can("sales.write")) -> dict:
    if body.group_id and db.get(CustomerGroup, body.group_id) is None:
        raise DomainError(422, "Unknown customer group.")
    customer = Customer(code=next_number(db, "C", today()), **body.model_dump())
    db.add(customer)
    db.flush()
    log(db, user, "customer", customer.id, "created", f"Customer {customer.name} created")
    db.commit()
    return get_customer(customer.id, db, user)


@router.put("/customers/{customer_id}")
def update_customer(customer_id: int, body: CustomerIn, db: Db, user: can("sales.write")) -> dict:
    customer = get_or_404(db, Customer, customer_id, "Customer")
    if body.group_id and db.get(CustomerGroup, body.group_id) is None:
        raise DomainError(422, "Unknown customer group.")
    if body.credit_limit != customer.credit_limit:
        log(db, user, "customer", customer.id, "credit_limit",
            f"Credit limit {rupiah(customer.credit_limit)} → {rupiah(body.credit_limit)}")
    for field, value in body.model_dump().items():
        setattr(customer, field, value)
    log(db, user, "customer", customer.id, "updated", "Details updated")
    db.commit()
    return get_customer(customer.id, db, user)


# ---------------------------------------------------------------- suppliers


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=40)
    address: str | None = Field(None, max_length=250)
    city: str | None = Field(None, max_length=80)
    payment_terms_days: int = Field(30, ge=0, le=365)
    active: bool = True


def supplier_row(s: Supplier, balance: tuple[int, int] = (0, 0)) -> dict:
    return {"id": s.id, "code": s.code, "name": s.name, "email": s.email, "phone": s.phone, "address": s.address,
            "city": s.city, "payment_terms_days": s.payment_terms_days, "active": s.active,
            "balance": balance[0], "overdue": balance[1]}


@router.get("/suppliers")
def list_suppliers(db: Db, _: can("purchasing.read"), params: Params, active: bool | None = True) -> dict:
    stmt = select(Supplier)
    if params.q:
        stmt = stmt.where(or_(Supplier.name.ilike(like(params.q)), Supplier.code.ilike(like(params.q)),
                              Supplier.email.ilike(like(params.q))))
    if active is not None:
        stmt = stmt.where(Supplier.active == active)
    page = paginate(db, stmt, params, lambda s: s, sortable={"code": Supplier.code, "name": Supplier.name,
                                                               "city": Supplier.city}, default_sort=[Supplier.name])
    balances = _balances(db, "supplier", [s.id for s in page["items"]])
    page["items"] = [supplier_row(s, balances.get(s.id, (0, 0))) for s in page["items"]]
    return page


@router.get("/suppliers/{supplier_id}")
def get_supplier(supplier_id: int, db: Db, _: can("purchasing.read")) -> dict:
    s = get_or_404(db, Supplier, supplier_id, "Supplier")
    orders = db.scalars(select(PurchaseOrder).filter_by(supplier_id=s.id).order_by(PurchaseOrder.id.desc()).limit(10))
    bills = db.scalars(select(Invoice).filter_by(kind="supplier", supplier_id=s.id).order_by(Invoice.id.desc()).limit(10))
    spend = db.scalar(select(func.coalesce(func.sum(Invoice.subtotal), 0)).where(
        Invoice.kind == "supplier", Invoice.supplier_id == s.id, Invoice.status != "cancelled"))
    return {
        **supplier_row(s, _balances(db, "supplier", [s.id]).get(s.id, (0, 0))),
        "lifetime_spend": spend,
        "recent_orders": [{"id": o.id, "number": o.number, "order_date": o.order_date, "status": o.status,
                           "total": o.total} for o in orders],
        "recent_bills": [{"id": i.id, "number": i.number, "issue_date": i.issue_date, "due_date": i.due_date,
                          "status": i.status, "total": i.total, "balance": i.balance} for i in bills],
        "activity": timeline(db, "supplier", s.id),
    }


@router.post("/suppliers", status_code=201)
def create_supplier(body: SupplierIn, db: Db, user: can("purchasing.write")) -> dict:
    supplier = Supplier(code=next_number(db, "S", today()), **body.model_dump())
    db.add(supplier)
    db.flush()
    log(db, user, "supplier", supplier.id, "created", f"Supplier {supplier.name} created")
    db.commit()
    return get_supplier(supplier.id, db, user)


@router.put("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, body: SupplierIn, db: Db, user: can("purchasing.write")) -> dict:
    supplier = get_or_404(db, Supplier, supplier_id, "Supplier")
    for field, value in body.model_dump().items():
        setattr(supplier, field, value)
    log(db, user, "supplier", supplier.id, "updated", "Details updated")
    db.commit()
    return get_supplier(supplier.id, db, user)
