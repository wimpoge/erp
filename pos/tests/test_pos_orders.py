from datetime import timedelta

from sqlalchemy import func, select

from erp_service.models import SalesOrder
from erp_service.models import Store as ErpStore
from pos_service.models import Customer, CustomerGroup, Order, ProductStock, utcnow
from pos_service.orders import _load, push_due, push_payload
from pos_service.sync import run_sync


def stocked_product(http, location_id, min_qty=2) -> dict:
    return next(p for p in http.get("/api/products", params={"location_id": location_id}).json()
                if p["on_hand"] >= min_qty)


def sell(http, qty=1, customer_id=None, pay=None, location_id=1) -> tuple[dict, dict]:
    product = stocked_product(http, location_id, qty)
    body = {
        "location_id": location_id,
        "register_id": http.get("/api/locations").json()[0]["registers"][0]["id"],
        "customer_id": customer_id,
        "lines": [{"product_id": product["id"], "qty": qty}],
        "payments": [{"method": "cash", "amount": pay or product["price"] * qty}],
    }
    return product, http.post("/api/orders", json=body)


def erp_orders(erp_db) -> int:
    with erp_db() as db:
        return db.scalar(select(func.count()).select_from(SalesOrder))


def test_sale_is_saved_stock_taken_and_pushed(synced_pos, pos_db, erp_db):
    product, r = sell(synced_pos, qty=2)

    assert r.status_code == 201
    order = synced_pos.get(f"/api/orders/{r.json()['id']}").json()
    assert order["total"] == product["price"] * 2
    assert order["number"].startswith("KG01-")
    # The push ran as a background task after the response.
    assert order["push_status"] == "sent" and order["erp_number"].startswith("SO-")
    assert erp_orders(erp_db) == 1
    after = next(p for p in synced_pos.get("/api/products", params={"location_id": 1}).json()
                 if p["id"] == product["id"])
    assert after["on_hand"] == product["on_hand"] - 2


def test_group_discount_and_change(synced_pos, pos_db):
    with pos_db() as db:
        member = db.scalar(select(Customer).join(CustomerGroup).where(CustomerGroup.discount_rate == 5))
    product = stocked_product(synced_pos, 1)
    body = {
        "location_id": 1,
        "customer_id": member.id,
        "lines": [{"product_id": product["id"], "qty": 1}],
        "payments": [{"method": "card", "amount": 1000}, {"method": "cash", "amount": product["price"]}],
    }
    order = synced_pos.post("/api/orders", json=body).json()
    assert order["discount"] == product["price"] * 5 // 100
    assert order["total"] == product["price"] - order["discount"]
    assert order["change"] == 1000 + order["discount"]


def test_cannot_sell_more_than_in_stock(synced_pos):
    product = stocked_product(synced_pos, 1, 1)
    body = {"location_id": 1, "lines": [{"product_id": product["id"], "qty": product["on_hand"] + 1}],
            "payments": [{"method": "cash", "amount": 10**9}]}
    r = synced_pos.post("/api/orders", json=body)
    assert r.status_code == 409 and "in stock" in r.json()["detail"]


def test_payment_must_cover_total_and_change_only_from_cash(synced_pos):
    product = stocked_product(synced_pos, 1, 1)
    short = {"location_id": 1, "lines": [{"product_id": product["id"], "qty": 1}],
             "payments": [{"method": "cash", "amount": product["price"] - 1}]}
    assert synced_pos.post("/api/orders", json=short).status_code == 422
    card_over = {**short, "payments": [{"method": "card", "amount": product["price"] + 5000}]}
    assert synced_pos.post("/api/orders", json=card_over).status_code == 422


def test_erp_outage_queues_the_push_and_retry_sends_it(synced_pos, pos_db, erp_http, erp, erp_db):
    erp_http.app.state.settings.fail_rate = 1.0
    _, r = sell(synced_pos)
    order = synced_pos.get(f"/api/orders/{r.json()['id']}").json()
    assert order["push_status"] == "pending" and order["push_attempts"] == 1
    assert "503" in order["last_push_error"] and order["next_push_at"] is not None
    assert erp_orders(erp_db) == 0

    # Backoff not over yet: nothing is retried.
    assert synced_pos.post("/api/orders/push-pending").json()["tried"] == 0

    erp_http.app.state.settings.fail_rate = 0.0
    with pos_db() as db:
        db.get(Order, order["id"]).next_push_at = utcnow() - timedelta(seconds=1)
        db.commit()
        assert push_due(db, erp, max_attempts=8) == {"tried": 1, "sent": 1, "pending": 0, "failed": 0}
    assert erp_orders(erp_db) == 1
    log = synced_pos.get(f"/api/orders/{order['id']}").json()["push_log"]
    assert [a["ok"] for a in log] == [False, True]


def test_push_is_idempotent_when_the_erp_already_has_the_order(synced_pos, pos_db, erp_http, erp, erp_db):
    # Simulate "the ERP saved it but we never saw the answer": the order exists there already.
    erp_http.app.state.settings.fail_rate = 1.0
    _, r = sell(synced_pos)
    erp_http.app.state.settings.fail_rate = 0.0
    with pos_db() as db:
        order = db.scalar(_load().where(Order.id == r.json()["id"]))
        erp.request("POST", "/api/sales-orders", json=push_payload(order))
    assert erp_orders(erp_db) == 1

    pushed = synced_pos.post(f"/api/orders/{r.json()['id']}/push").json()
    assert pushed["push_status"] == "sent"
    assert erp_orders(erp_db) == 1


def test_rejected_push_is_not_retried(synced_pos, erp_http, erp_db):
    erp_http.app.state.settings.fail_rate = 1.0
    _, r = sell(synced_pos)
    erp_http.app.state.settings.fail_rate = 0.0
    with erp_db() as db:  # the store closes in the ERP before the queued order gets through
        db.scalars(select(ErpStore).order_by(ErpStore.id)).first().active = False
        db.commit()

    pushed = synced_pos.post(f"/api/orders/{r.json()['id']}/push").json()

    # A 422 won't change on retry: stop and leave it for a person to look at.
    assert pushed["push_status"] == "failed" and pushed["next_push_at"] is None
    assert pushed["push_log"][-1]["status_code"] == 422


def test_sync_does_not_hand_back_units_the_erp_has_not_seen(synced_pos, pos_db, erp_http, erp):
    erp_http.app.state.settings.fail_rate = 1.0
    product, _ = sell(synced_pos, qty=2)
    with pos_db() as db:
        run_sync(db, erp)
        stock = db.scalar(select(ProductStock).filter_by(product_id=product["id"], location_id=1))
        assert stock.on_hand == product["on_hand"] - 2
