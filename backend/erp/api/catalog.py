"""Products, categories, warehouses."""

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ..models import Category, Product, StockLevel, StockMove, Warehouse
from ..services.common import DomainError, get_or_404, log, rupiah
from ..services.inventory import availability, incoming_qty, reserved_qty
from .deps import Db, Params, can, like, paginate
from .serializers import timeline, user_ref, warehouse_ref

router = APIRouter(prefix="/api", tags=["catalog"])


# ---------------------------------------------------------------- categories


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.get("/categories")
def list_categories(db: Db, _: can("catalog.read")) -> list[dict]:
    counts = dict(db.execute(select(Product.category_id, func.count()).group_by(Product.category_id)).all())
    return [{"id": c.id, "name": c.name, "products": counts.get(c.id, 0)}
            for c in db.scalars(select(Category).order_by(Category.name))]


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, db: Db, _: can("catalog.write")) -> dict:
    category = Category(name=body.name.strip())
    db.add(category)
    _commit_unique(db, "A category with that name already exists.")
    return {"id": category.id, "name": category.name, "products": 0}


@router.patch("/categories/{category_id}")
def rename_category(category_id: int, body: CategoryIn, db: Db, _: can("catalog.write")) -> dict:
    category = get_or_404(db, Category, category_id, "Category")
    category.name = body.name.strip()
    _commit_unique(db, "A category with that name already exists.")
    return {"id": category.id, "name": category.name}


def _commit_unique(db, message: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DomainError(409, message) from None


# ---------------------------------------------------------------- products


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(None, max_length=2000)
    category_id: int | None = None
    brand: str | None = Field(None, max_length=60)
    barcode: str | None = Field(None, max_length=20)
    unit: str = Field("pcs", min_length=1, max_length=10)
    sale_price: int = Field(ge=0)
    avg_cost: int | None = Field(None, ge=0, description="Only for a new product without stock yet")
    reorder_point: int = Field(0, ge=0)
    active: bool = True


def product_row(p: Product, on_hand: int = 0, reserved: int = 0, incoming: int = 0) -> dict:
    return {
        "id": p.id, "sku": p.sku, "name": p.name, "brand": p.brand, "barcode": p.barcode, "unit": p.unit,
        "category": {"id": p.category.id, "name": p.category.name} if p.category else None,
        "sale_price": p.sale_price, "avg_cost": p.avg_cost, "reorder_point": p.reorder_point, "active": p.active,
        "on_hand": on_hand, "reserved": reserved, "available": on_hand - reserved, "incoming": incoming,
        "low_stock": p.reorder_point > 0 and on_hand <= p.reorder_point,
    }


@router.get("/products")
def list_products(
    db: Db,
    _: can("catalog.read"),
    params: Params,
    category_id: int | None = None,
    active: bool | None = True,
    low_stock: bool = False,
    warehouse_id: int | None = None,
) -> dict:
    """Products with stock totals (all warehouses, or one)."""
    stock = select(StockLevel.product_id, func.sum(StockLevel.on_hand).label("on_hand")).group_by(StockLevel.product_id)
    if warehouse_id:
        stock = stock.where(StockLevel.warehouse_id == warehouse_id)
    stock = stock.subquery()
    on_hand = func.coalesce(stock.c.on_hand, 0)
    stmt = select(Product, on_hand).options(selectinload(Product.category)).outerjoin(stock, stock.c.product_id == Product.id)
    if params.q:
        stmt = stmt.where(or_(Product.name.ilike(like(params.q)), Product.sku.ilike(like(params.q)),
                              Product.brand.ilike(like(params.q)), Product.barcode == params.q))
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    if active is not None:
        stmt = stmt.where(Product.active == active)
    if low_stock:
        stmt = stmt.where(Product.reorder_point > 0, on_hand <= Product.reorder_point)

    page = paginate(db, stmt, params, lambda row: row, scalars=False,
                    sortable={"sku": Product.sku, "name": Product.name, "price": Product.sale_price,
                              "on_hand": on_hand, "cost": Product.avg_cost},
                    default_sort=[Product.name])
    ids = [p.id for p, _ in page["items"]]
    reserved, incoming = reserved_qty(db, ids), incoming_qty(db, ids)

    def total(m: dict, pid: int) -> int:
        return sum(q for (p, w), q in m.items() if p == pid and (warehouse_id is None or w == warehouse_id))

    page["items"] = [product_row(p, oh, total(reserved, p.id), total(incoming, p.id)) for p, oh in page["items"]]
    return page


@router.get("/products/{product_id}")
def get_product(product_id: int, db: Db, _: can("catalog.read")) -> dict:
    product = get_or_404(db, Product, product_id, "Product")
    per_warehouse = availability(db, product)
    moves = db.scalars(
        select(StockMove).options(selectinload(StockMove.warehouse), selectinload(StockMove.user))
        .filter_by(product_id=product.id).order_by(StockMove.moved_at.desc(), StockMove.id.desc()).limit(20)
    )
    totals = {k: sum(r[k] for r in per_warehouse) for k in ("on_hand", "reserved", "incoming")}
    return {
        **product_row(product, totals["on_hand"], totals["reserved"], totals["incoming"]),
        "description": product.description,
        "stock_value": totals["on_hand"] * product.avg_cost,
        "warehouses": per_warehouse,
        "recent_moves": [move_out(m) for m in moves],
        "activity": timeline(db, "product", product.id),
    }


def move_out(m: StockMove) -> dict:
    return {"id": m.id, "at": m.moved_at, "warehouse": warehouse_ref(m.warehouse), "qty": m.qty,
            "unit_cost": m.unit_cost, "kind": m.kind, "ref_type": m.ref_type, "ref_id": m.ref_id,
            "ref_number": m.ref_number, "user": user_ref(m.user)}


def _apply_product(db, product: Product, body: ProductIn) -> None:
    if body.category_id is not None and db.get(Category, body.category_id) is None:
        raise DomainError(422, "Unknown category.")
    for field in ("sku", "name", "description", "category_id", "brand", "unit", "sale_price", "reorder_point", "active"):
        setattr(product, field, getattr(body, field))
    product.sku = product.sku.strip().upper()
    product.barcode = body.barcode or None


@router.post("/products", status_code=201)
def create_product(body: ProductIn, db: Db, user: can("catalog.write")) -> dict:
    product = Product(avg_cost=body.avg_cost or 0)
    _apply_product(db, product, body)
    db.add(product)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise DomainError(409, "SKU or barcode is already used by another product.") from None
    log(db, user, "product", product.id, "created", f"Product {product.sku} created")
    db.commit()
    return get_product(product.id, db, user)


@router.put("/products/{product_id}")
def update_product(product_id: int, body: ProductIn, db: Db, user: can("catalog.write")) -> dict:
    product = get_or_404(db, Product, product_id, "Product")
    before = {"price": product.sale_price, "active": product.active}
    _apply_product(db, product, body)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise DomainError(409, "SKU or barcode is already used by another product.") from None
    changes = []
    if before["price"] != product.sale_price:
        changes.append(f"price {rupiah(before['price'])} → {rupiah(product.sale_price)}")
    if before["active"] != product.active:
        changes.append("activated" if product.active else "archived")
    log(db, user, "product", product.id, "updated", "Updated" + (": " + ", ".join(changes) if changes else ""))
    db.commit()
    return get_product(product.id, db, user)


# ---------------------------------------------------------------- warehouses


class WarehouseIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    city: str = Field(min_length=1, max_length=80)
    address: str | None = Field(None, max_length=250)
    active: bool = True


@router.get("/warehouses")
def list_warehouses(db: Db, _: can("catalog.read"),
                    include_inactive: Annotated[bool, Query()] = False) -> list[dict]:
    stats = {wid: (units, value) for wid, units, value in db.execute(
        select(StockLevel.warehouse_id, func.sum(StockLevel.on_hand), func.sum(StockLevel.on_hand * Product.avg_cost))
        .join(Product).group_by(StockLevel.warehouse_id))}
    stmt = select(Warehouse).order_by(Warehouse.code)
    if not include_inactive:
        stmt = stmt.where(Warehouse.active)
    return [{**warehouse_ref(w), "city": w.city, "address": w.address, "active": w.active,
             "units": stats.get(w.id, (0, 0))[0], "stock_value": stats.get(w.id, (0, 0))[1]}
            for w in db.scalars(stmt)]


@router.post("/warehouses", status_code=201)
def create_warehouse(body: WarehouseIn, db: Db, _: can("catalog.write")) -> dict:
    warehouse = Warehouse(**{**body.model_dump(), "code": body.code.strip().upper()})
    db.add(warehouse)
    _commit_unique(db, "That warehouse code is already used.")
    return {**warehouse_ref(warehouse), "city": warehouse.city, "address": warehouse.address,
            "active": warehouse.active, "units": 0, "stock_value": 0}


@router.put("/warehouses/{warehouse_id}")
def update_warehouse(warehouse_id: int, body: WarehouseIn, db: Db, _: can("catalog.write")) -> dict:
    warehouse = get_or_404(db, Warehouse, warehouse_id, "Warehouse")
    if not body.active and warehouse.active:
        stock = db.scalar(select(func.coalesce(func.sum(StockLevel.on_hand), 0)).filter_by(warehouse_id=warehouse.id))
        if stock:
            raise DomainError(409, f"{warehouse.name} still holds {stock} unit(s). Transfer them out first.")
    for field, value in body.model_dump().items():
        setattr(warehouse, field, value)
    warehouse.code = warehouse.code.strip().upper()
    _commit_unique(db, "That warehouse code is already used.")
    return {**warehouse_ref(warehouse), "city": warehouse.city, "address": warehouse.address, "active": warehouse.active}
