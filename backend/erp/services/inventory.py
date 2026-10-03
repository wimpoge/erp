"""Stock: the only place that changes quantities. Every change is a StockMove in the ledger."""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Adjustment,
    AdjustmentLine,
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    SalesOrder,
    SalesOrderLine,
    StockLevel,
    StockMove,
    Transfer,
    TransferLine,
    User,
    Warehouse,
)
from .common import DomainError, at_noon, log, next_number, stamp

OPEN_SALES = ("confirmed", "partially_delivered")
OPEN_PURCHASES = ("confirmed", "partially_received")


@dataclass(frozen=True)
class Ref:
    type: str
    id: int
    number: str


def post_move(
    db: Session,
    *,
    product: Product,
    warehouse: Warehouse,
    qty: int,
    kind: str,
    unit_cost: int,
    ref: Ref | None,
    user: User | None,
    at: datetime,
) -> StockMove:
    """Change on-hand stock by `qty` (signed) and write the ledger line. Never below zero."""
    level = db.scalar(
        select(StockLevel).filter_by(product_id=product.id, warehouse_id=warehouse.id).with_for_update()
    )
    if level is None:
        level = StockLevel(product_id=product.id, warehouse_id=warehouse.id, on_hand=0)
        db.add(level)
    if level.on_hand + qty < 0:
        raise DomainError(
            409,
            f"Not enough {product.name} ({product.sku}) in {warehouse.name}: "
            f"{level.on_hand} on hand, {-qty} needed.",
        )
    level.on_hand += qty
    move = StockMove(
        moved_at=at, product_id=product.id, warehouse_id=warehouse.id, qty=qty, unit_cost=unit_cost, kind=kind,
        ref_type=ref.type if ref else None, ref_id=ref.id if ref else None, ref_number=ref.number if ref else None,
        user_id=user.id if user else None,
    )
    db.add(move)
    db.flush()
    return move


def total_on_hand(db: Session, product_id: int) -> int:
    return db.scalar(select(func.coalesce(func.sum(StockLevel.on_hand), 0)).filter_by(product_id=product_id))


def apply_receipt_cost(db: Session, product: Product, qty: int, unit_cost: int) -> None:
    """Moving average: blend the incoming units' cost with the units already in stock.

    Call before posting the receipt move, while on-hand still excludes the new units.
    """
    existing = total_on_hand(db, product.id)
    if existing + qty <= 0:
        return
    product.avg_cost = (existing * product.avg_cost + qty * unit_cost + (existing + qty) // 2) // (existing + qty)


# ---------------------------------------------------------------- availability


def reserved_qty(db: Session, product_ids: list[int] | None = None) -> dict[tuple[int, int], int]:
    """Units promised on confirmed sales orders but not shipped yet, per (product, warehouse)."""
    stmt = (
        select(SalesOrderLine.product_id, SalesOrder.warehouse_id,
               func.sum(SalesOrderLine.qty - SalesOrderLine.qty_delivered))
        .join(SalesOrder)
        .where(SalesOrder.status.in_(OPEN_SALES))
        .group_by(SalesOrderLine.product_id, SalesOrder.warehouse_id)
    )
    if product_ids is not None:
        stmt = stmt.where(SalesOrderLine.product_id.in_(product_ids))
    return {(p, w): q for p, w, q in db.execute(stmt)}


def incoming_qty(db: Session, product_ids: list[int] | None = None) -> dict[tuple[int, int], int]:
    """Units ordered from suppliers but not received yet, per (product, warehouse)."""
    stmt = (
        select(PurchaseOrderLine.product_id, PurchaseOrder.warehouse_id,
               func.sum(PurchaseOrderLine.qty - PurchaseOrderLine.qty_received))
        .join(PurchaseOrder)
        .where(PurchaseOrder.status.in_(OPEN_PURCHASES))
        .group_by(PurchaseOrderLine.product_id, PurchaseOrder.warehouse_id)
    )
    if product_ids is not None:
        stmt = stmt.where(PurchaseOrderLine.product_id.in_(product_ids))
    return {(p, w): q for p, w, q in db.execute(stmt)}


def availability(db: Session, product: Product) -> list[dict]:
    """Per warehouse: on hand, reserved for customers, available to promise, incoming."""
    on_hand = {w: q for w, q in db.execute(
        select(StockLevel.warehouse_id, StockLevel.on_hand).filter_by(product_id=product.id))}
    reserved = reserved_qty(db, [product.id])
    incoming = incoming_qty(db, [product.id])
    rows = []
    for wh in db.scalars(select(Warehouse).filter_by(active=True).order_by(Warehouse.code)):
        oh = on_hand.get(wh.id, 0)
        res = reserved.get((product.id, wh.id), 0)
        rows.append({
            "warehouse": {"id": wh.id, "code": wh.code, "name": wh.name},
            "on_hand": oh, "reserved": res, "available": oh - res, "incoming": incoming.get((product.id, wh.id), 0),
        })
    return rows


# ---------------------------------------------------------------- transfers


@dataclass
class QtyLine:
    product_id: int
    qty: int


def _products(db: Session, ids: list[int]) -> dict[int, Product]:
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)))}
    missing = set(ids) - products.keys()
    if missing:
        raise DomainError(422, f"Unknown product id(s): {sorted(missing)}.")
    return products


def _merge(lines: list[QtyLine]) -> list[QtyLine]:
    merged: dict[int, int] = {}
    for line in lines:
        merged[line.product_id] = merged.get(line.product_id, 0) + line.qty
    return [QtyLine(p, q) for p, q in merged.items()]


def create_transfer(db: Session, user: User, from_id: int, to_id: int, on: date, lines: list[QtyLine],
                    note: str | None = None) -> Transfer:
    if from_id == to_id:
        raise DomainError(422, "Source and destination must be different warehouses.")
    source, dest = db.get(Warehouse, from_id), db.get(Warehouse, to_id)
    if source is None or dest is None or not (source.active and dest.active):
        raise DomainError(422, "Pick two active warehouses.")
    if not lines:
        raise DomainError(422, "Add at least one product.")
    lines = _merge(lines)
    _products(db, [li.product_id for li in lines])
    transfer = Transfer(number=next_number(db, "TR", on), from_warehouse_id=from_id, to_warehouse_id=to_id,
                        transfer_date=on, created_at=stamp(on), note=note, created_by_id=user.id,
                        lines=[TransferLine(product_id=li.product_id, qty=li.qty) for li in lines])
    db.add(transfer)
    db.flush()
    log(db, user, "transfer", transfer.id, "created", f"Transfer {transfer.number} drafted: {source.name} → {dest.name}")
    return transfer


def validate_transfer(db: Session, user: User, transfer: Transfer) -> Transfer:
    if transfer.status != "draft":
        raise DomainError(409, f"Transfer {transfer.number} is {transfer.status}.")
    ref = Ref("transfer", transfer.id, transfer.number)
    at = at_noon(transfer.transfer_date)
    for line in transfer.lines:
        cost = line.product.avg_cost
        post_move(db, product=line.product, warehouse=transfer.from_warehouse, qty=-line.qty, kind="transfer_out",
                  unit_cost=cost, ref=ref, user=user, at=at)
        post_move(db, product=line.product, warehouse=transfer.to_warehouse, qty=line.qty, kind="transfer_in",
                  unit_cost=cost, ref=ref, user=user, at=at)
    transfer.status = "done"
    log(db, user, "transfer", transfer.id, "validated", f"{transfer.number}: {sum(li.qty for li in transfer.lines)} unit(s) moved "
        f"{transfer.from_warehouse.name} → {transfer.to_warehouse.name}")
    return transfer


def cancel_transfer(db: Session, user: User, transfer: Transfer) -> Transfer:
    if transfer.status != "draft":
        raise DomainError(409, "Only a draft transfer can be cancelled.")
    transfer.status = "cancelled"
    log(db, user, "transfer", transfer.id, "cancelled", f"{transfer.number} cancelled")
    return transfer


# ---------------------------------------------------------------- stock counts


@dataclass
class CountLine:
    product_id: int
    counted_qty: int


def create_adjustment(db: Session, user: User, warehouse_id: int, on: date, reason: str,
                      lines: list[CountLine]) -> Adjustment:
    warehouse = db.get(Warehouse, warehouse_id)
    if warehouse is None or not warehouse.active:
        raise DomainError(422, "Pick an active warehouse.")
    if not lines:
        raise DomainError(422, "Add at least one product.")
    ids = [li.product_id for li in lines]
    if len(set(ids)) != len(ids):
        raise DomainError(422, "Each product can only be counted once per adjustment.")
    _products(db, ids)
    adj = Adjustment(number=next_number(db, "ADJ", on), warehouse_id=warehouse_id, adjustment_date=on, created_at=stamp(on),
                     reason=reason, created_by_id=user.id,
                     lines=[AdjustmentLine(product_id=li.product_id, counted_qty=li.counted_qty) for li in lines])
    db.add(adj)
    db.flush()
    log(db, user, "adjustment", adj.id, "created", f"Stock count {adj.number} drafted for {warehouse.name}")
    return adj


def validate_adjustment(db: Session, user: User | None, adj: Adjustment, kind: str = "adjustment") -> Adjustment:
    if adj.status != "draft":
        raise DomainError(409, f"Adjustment {adj.number} is {adj.status}.")
    ref = Ref("adjustment", adj.id, adj.number)
    changed = 0
    for line in adj.lines:
        level = db.scalar(select(StockLevel).filter_by(product_id=line.product_id, warehouse_id=adj.warehouse_id))
        line.system_qty = level.on_hand if level else 0
        diff = line.counted_qty - line.system_qty
        if diff:
            changed += 1
            post_move(db, product=line.product, warehouse=adj.warehouse, qty=diff, kind=kind,
                      unit_cost=line.product.avg_cost, ref=ref, user=user, at=at_noon(adj.adjustment_date))
    adj.status = "done"
    log(db, user, "adjustment", adj.id, "validated", f"{adj.number}: {changed} product(s) corrected in {adj.warehouse.name}")
    return adj


def cancel_adjustment(db: Session, user: User, adj: Adjustment) -> Adjustment:
    if adj.status != "draft":
        raise DomainError(409, "Only a draft stock count can be cancelled.")
    adj.status = "cancelled"
    log(db, user, "adjustment", adj.id, "cancelled", f"{adj.number} cancelled")
    return adj
