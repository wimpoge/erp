import uuid

from sqlalchemy import func, select

from erp_service.models import Product, SalesOrder, Stock, Store


def token(erp_http) -> dict:
    r = erp_http.post("/oauth/token", json={"client_id": "pos-dev", "client_secret": "pos-dev-secret", "app_code": "POS"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_lists_need_a_token(erp_http):
    assert erp_http.get("/api/products").status_code == 401
    assert erp_http.get("/api/products", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_wrong_secret_or_app_code_is_rejected(erp_http):
    for body in (
        {"client_id": "pos-dev", "client_secret": "wrong", "app_code": "POS"},
        {"client_id": "pos-dev", "client_secret": "pos-dev-secret", "app_code": "OTHER"},
    ):
        assert erp_http.post("/oauth/token", json=body).status_code == 401


def test_revoked_token_stops_working(erp_http):
    headers = token(erp_http)
    assert erp_http.delete("/oauth/tokens", headers=headers).status_code == 204
    assert erp_http.get("/api/stores", headers=headers).status_code == 401


def test_pagination_and_public_ids_only(erp_http):
    headers = token(erp_http)
    first = erp_http.get("/api/products", params={"page": 1, "page_size": 10}, headers=headers).json()
    second = erp_http.get("/api/products", params={"page": 2, "page_size": 10}, headers=headers).json()
    assert first["total"] == 15
    assert len(first["items"]) == 10 and len(second["items"]) == 5
    assert len(first["items"][0]["id"]) == 36  # a UUID, never the integer key


def test_stores_carry_their_registers(erp_http):
    stores = erp_http.get("/api/stores", headers=token(erp_http)).json()["items"]
    assert [len(s["registers"]) for s in stores] == [2, 2]


def _order_body(erp_http, headers, external_id="pos-1", qty=2):
    store = erp_http.get("/api/stores", headers=headers).json()["items"][0]
    product = erp_http.get("/api/products", headers=headers).json()["items"][0]
    return {
        "external_id": external_id,
        "store_id": store["id"],
        "lines": [{"product_id": product["id"], "qty": qty, "unit_price": product["price"]}],
    }


def _stock(erp_db, body) -> int:
    with erp_db() as db:
        return db.scalar(
            select(Stock.on_hand).join(Product).join(Store, Store.id == Stock.store_id).where(
                Store.public_id == uuid.UUID(body["store_id"]),
                Product.public_id == uuid.UUID(body["lines"][0]["product_id"]),
            )
        )


def test_sales_order_is_idempotent_on_external_id(erp_http, erp_db):
    headers = token(erp_http)
    body = _order_body(erp_http, headers)
    stock_before = _stock(erp_db, body)

    first = erp_http.post("/api/sales-orders", json=body, headers=headers)
    again = erp_http.post("/api/sales-orders", json=body, headers=headers)

    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["id"] == again.json()["id"]
    assert first.json()["number"].startswith("SO-")
    with erp_db() as db:
        assert db.scalar(select(func.count()).select_from(SalesOrder)) == 1
    assert _stock(erp_db, body) == max(0, stock_before - 2)  # taken once, never below zero


def test_sales_order_rejects_unknown_product(erp_http):
    headers = token(erp_http)
    body = _order_body(erp_http, headers)
    body["lines"][0]["product_id"] = "00000000-0000-0000-0000-000000000000"
    assert erp_http.post("/api/sales-orders", json=body, headers=headers).status_code == 422


def test_failure_injection(erp_http):
    erp_http.app.state.settings.fail_rate = 1.0
    headers = token(erp_http)
    assert erp_http.post("/api/sales-orders", json=_order_body(erp_http, headers), headers=headers).status_code == 503
