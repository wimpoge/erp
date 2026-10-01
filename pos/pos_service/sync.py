"""Pull master data from the ERP into POS tables.

Every ERP list goes through one generic `mirror`: shape each row, match it on a key,
insert or update it, then deactivate (or delete) the rows the ERP no longer returns.
Every change is logged as a SyncEvent. Two safety rules:

* an ERP answer with 0 rows never empties a table that has rows (an API change or a
  bad filter looks exactly like that), and
* a row that fails is logged with its error and skipped; it does not stop the run.
"""

import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .erp_client import ErpClient
from .models import (
    Customer,
    CustomerGroup,
    Location,
    Order,
    OrderLine,
    Product,
    ProductStock,
    Register,
    SyncEvent,
    SyncRun,
    SyncState,
    utcnow,
)


@dataclass
class MirrorResult:
    rows: int = 0
    inserted: int = 0
    updated: int = 0
    removed: int = 0
    errors: int = 0
    skipped: bool = False


def _uuid(value) -> uuid.UUID:
    return uuid.UUID(str(value))


def _lookup(ids: dict[uuid.UUID, int], erp_id, what: str) -> int:
    try:
        return ids[_uuid(erp_id)]
    except KeyError:
        raise ValueError(f"unknown {what} {erp_id}") from None


def _id_map(db: Session, model) -> dict[uuid.UUID, int]:
    return dict(db.execute(select(model.erp_public_id, model.id)).all())


def mirror(
    db: Session,
    run: SyncRun,
    table: str,
    model,
    rows: list[dict],
    shape: Callable[[dict], dict],
    *,
    key: tuple[str, ...] = ("erp_public_id",),
    scope: dict | None = None,
    on_missing: Literal["deactivate", "delete"] = "deactivate",
) -> MirrorResult:
    """Make the POS rows of `model` (within `scope`) match `rows` from the ERP."""
    scope = scope or {}
    result = MirrorResult(rows=len(rows))

    def log(action: str, erp_id=None, message: str | None = None) -> None:
        db.add(SyncEvent(run_id=run.id, table=table, action=action,
                         erp_public_id=str(erp_id) if erp_id else None, message=message))

    existing = {tuple(getattr(obj, f) for f in key): obj for obj in db.scalars(select(model).filter_by(**scope))}
    if not rows and existing:
        result.skipped = True
        log("skipped", message=f"ERP returned 0 rows; kept {len(existing)} existing rows")
        return result

    seen: set[tuple] = set()
    for raw in rows:
        erp_id = raw.get("id")
        if key == ("erp_public_id",) and erp_id:
            # Mark it seen up front: a row that fails to shape must not get deactivated.
            seen.add((_uuid(erp_id),))
        try:
            with db.begin_nested():
                values = {**shape(raw), **scope}
                k = tuple(values[f] for f in key)
                seen.add(k)
                obj = existing.get(k)
                if obj is None:
                    obj = model(**values)
                    db.add(obj)
                    db.flush()
                    existing[k] = obj
                    result.inserted += 1
                    log("insert", erp_id)
                else:
                    changed = [f for f, v in values.items() if getattr(obj, f) != v]
                    if changed:
                        for f in changed:
                            setattr(obj, f, values[f])
                        db.flush()
                        result.updated += 1
                        log("update", erp_id, "changed: " + ", ".join(changed))
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the run
            result.errors += 1
            log("error", erp_id, f"{type(exc).__name__}: {exc}"[:500])

    for k, obj in existing.items():
        if k in seen:
            continue
        erp_id = getattr(obj, "erp_public_id", None)
        if on_missing == "delete":
            db.delete(obj)
            result.removed += 1
            log("delete", erp_id, f"key {k} no longer in ERP")
        elif obj.active:
            obj.active = False
            result.removed += 1
            log("deactivate", erp_id)
    db.flush()
    return result


# ---------------------------------------------------------------- shaping ERP rows


def shape_group(r: dict) -> dict:
    return {"erp_public_id": _uuid(r["id"]), "code": r["code"], "name": r["name"],
            "discount_rate": int(r["discount_rate"]), "active": bool(r["active"])}


def shape_location(r: dict) -> dict:
    return {"erp_public_id": _uuid(r["id"]), "code": r["code"], "name": r["name"],
            "city": r["city"], "active": bool(r["active"])}


def shape_product(r: dict) -> dict:
    return {"erp_public_id": _uuid(r["id"]), "sku": r["sku"], "name": r["name"], "barcode": r.get("barcode"),
            "brand": r["brand"], "category": r["category"], "price": int(r["price"]), "active": bool(r["active"])}


def pending_quantities(db: Session, location_id: int) -> dict[int, int]:
    """Units sold here that the ERP has not received yet (keyed by product id)."""
    stmt = (
        select(OrderLine.product_id, func.sum(OrderLine.qty))
        .join(Order)
        .where(Order.location_id == location_id, Order.push_status != "sent")
        .group_by(OrderLine.product_id)
    )
    return dict(db.execute(stmt).all())


# ---------------------------------------------------------------- the run


def run_sync(db: Session, erp: ErpClient) -> SyncRun:
    run = SyncRun()
    db.add(run)
    db.commit()
    failed_steps = 0

    def step(key: str, fn: Callable[[], MirrorResult]) -> None:
        nonlocal failed_steps
        state = db.get(SyncState, key) or SyncState(key=key, last_status="new")
        try:
            result = fn()
            state.last_status = "partial" if result.errors else ("skipped" if result.skipped else "ok")
            state.rows = result.rows
            if state.last_status == "ok":
                state.last_synced_at = utcnow()
            failed_steps += bool(result.errors)
            summary = asdict(result)
        except Exception as exc:  # ERP down, bad payload, ...: record it and go on with the next list
            db.rollback()
            failed_steps += 1
            db.add(SyncEvent(run_id=run.id, table=key, action="error", message=f"step failed: {exc}"[:500]))
            state = db.get(SyncState, key) or SyncState(key=key, last_status="new")
            state.last_status = "failed"
            summary = {"error": str(exc)[:200]}
        db.add(state)
        run.summary = {**run.summary, key: summary}
        db.commit()

    step("customer_groups", lambda: mirror(
        db, run, "customer_groups", CustomerGroup, erp.list_all("/api/customer-groups"), shape_group))

    stores: list[dict] = []

    def sync_locations() -> MirrorResult:
        stores.extend(erp.list_all("/api/stores"))
        return mirror(db, run, "locations", Location, stores, shape_location)

    step("locations", sync_locations)

    def sync_registers() -> MirrorResult:
        # Registers arrive nested inside each store; flatten them and rebuild the one-to-many link.
        location_ids = _id_map(db, Location)
        rows = [{**reg, "store_id": store["id"]} for store in stores for reg in store["registers"]]
        return mirror(db, run, "registers", Register, rows, lambda r: {
            "erp_public_id": _uuid(r["id"]),
            "location_id": _lookup(location_ids, r["store_id"], "store"),
            "code": r["code"], "name": r["name"], "active": bool(r["active"]),
        })

    if stores:
        step("registers", sync_registers)

    def sync_customers() -> MirrorResult:
        group_ids = _id_map(db, CustomerGroup)
        return mirror(db, run, "customers", Customer, erp.list_all("/api/customers"), lambda r: {
            "erp_public_id": _uuid(r["id"]), "code": r["code"], "name": r["name"], "phone": r["phone"],
            "email": r.get("email"), "active": bool(r["active"]),
            "group_id": _lookup(group_ids, r["group_id"], "customer group") if r.get("group_id") else None,
        })

    step("customers", sync_customers)
    step("products", lambda: mirror(db, run, "products", Product, erp.list_all("/api/products"), shape_product))

    product_ids = _id_map(db, Product)
    for location in db.scalars(select(Location).filter_by(active=True).order_by(Location.id)).all():

        def sync_stock(location=location) -> MirrorResult:
            pending = pending_quantities(db, location.id)

            def shape_stock(r: dict) -> dict:
                product_id = _lookup(product_ids, r["product_id"], "product")
                # The ERP has not seen our unpushed sales yet; don't hand those units back.
                return {"product_id": product_id, "on_hand": max(0, int(r["on_hand"]) - pending.get(product_id, 0))}

            rows = erp.list_all(f"/api/stores/{location.erp_public_id}/stock")
            return mirror(db, run, f"stock:{location.code}", ProductStock, rows, shape_stock,
                          key=("product_id", "location_id"), scope={"location_id": location.id},
                          on_missing="delete")

        step(f"stock:{location.code}", sync_stock)

    run.status = "ok" if failed_steps == 0 else "partial"
    run.finished_at = utcnow()
    db.commit()
    return run
