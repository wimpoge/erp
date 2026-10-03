"""What the POS tills need beyond selling: approvals, returns, loyalty, promotions, stock requests."""

from conftest import PASSWORD, ok
from test_access import integration_client, till_sale
from test_flows import buy, receive_all

API = "/api/integration/v1"


def setup(app, admin, qty: int = 10):
    receive_all(admin, buy(admin, {1: (qty, 600_000)}))
    pos = integration_client(admin, app)
    warehouse = ok(pos.get(f"{API}/warehouses"))["items"][0]
    product = next(p for p in ok(pos.get(f"{API}/products"))["items"] if p["sku"] == "PH-1")
    customers = {c["code"]: c for c in ok(pos.get(f"{API}/customers"))["items"]}
    return pos, warehouse, product, customers


def on_hand(pos, warehouse) -> int:
    rows = ok(pos.get(f"{API}/warehouses/{warehouse['id']}/stock"))["items"]
    return rows[0]["on_hand"] if rows else 0


def test_managers_approve_at_the_till_cashiers_do_not(app, admin):
    pos = integration_client(admin, app)
    assert "supervisors" in ok(pos.get(f"{API}/settings"))["features"]
    manager = ok(pos.post(f"{API}/supervisors/verify", json={"username": "manager", "password": PASSWORD}))
    assert manager == {"username": "manager", "full_name": "Manager"}
    cashier = pos.post(f"{API}/supervisors/verify", json={"username": "cashier", "password": PASSWORD})
    assert cashier.status_code == 403 and "can't approve" in cashier.json()["detail"]
    assert pos.post(f"{API}/supervisors/verify", json={"username": "manager", "password": "nope"}).status_code == 401


def test_return_puts_stock_back_and_refunds(app, admin):
    pos, warehouse, product, customers = setup(app, admin)
    ok(till_sale(pos, "sale-1", customers["C1"], warehouse, product, 3, [{"method": "cash", "amount": 3_330_000}]), 201)
    assert on_hand(pos, warehouse) == 7

    body = {"external_id": "ret-1", "order_external_id": "sale-1", "reason": "Cracked screen",
            "lines": [{"product_id": product["id"], "qty": 1}], "refunds": [{"method": "cash", "amount": 1_110_000}]}
    first = pos.post(f"{API}/sales-returns", json=body)
    again = pos.post(f"{API}/sales-returns", json=body)
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["number"] == again.json()["number"] and first.json()["total"] == 1_110_000
    assert on_hand(pos, warehouse) == 8

    order = ok(admin.get("/api/sales-orders", params={"q": first.json()["order_number"]}))["items"][0]
    detail = ok(admin.get(f"/api/sales-orders/{order['id']}"))
    assert detail["lines"][0]["qty_returned"] == 1 and detail["returns"][0]["reason"] == "Cracked screen"
    # Revenue is net of returns: 2 phones' worth left (before tax).
    assert ok(admin.get("/api/reports/dashboard"))["revenue_30d"] == 2_000_000

    wrong_refund = dict(body, external_id="ret-2", refunds=[{"method": "cash", "amount": 5}])
    assert pos.post(f"{API}/sales-returns", json=wrong_refund).status_code == 422
    too_many = dict(body, external_id="ret-3", lines=[{"product_id": product["id"], "qty": 3}],
                    refunds=[{"method": "cash", "amount": 3_330_000}])
    assert pos.post(f"{API}/sales-returns", json=too_many).status_code == 422
    # The rest comes back: exactly what is left of the order, to the rupiah.
    rest = ok(pos.post(f"{API}/sales-returns", json=dict(body, external_id="ret-4", lines=[
        {"product_id": product["id"], "qty": 2}], refunds=[{"method": "card", "amount": 2_220_000}])), 201)
    assert rest["total"] == 2_220_000 and on_hand(pos, warehouse) == 10
    assert pos.post(f"{API}/sales-returns", json=dict(body, external_id="ret-x", order_external_id="nope")).status_code == 404


def test_loyalty_points_earned_spent_and_taken_back(app, admin):
    pos, warehouse, product, customers = setup(app, admin)
    settings = ok(pos.get(f"{API}/settings"))
    assert settings["loyalty"] == {"earn_per": 10_000, "point_value": 100}
    reseller = customers["C2"]
    assert reseller["points"] == 0

    # 1 phone at the reseller's 10% off: 999,000, one point per 10,000 = 99 points.
    sale = pos.post(f"{API}/sales-orders", json={
        "external_id": "s1", "customer_id": reseller["id"], "warehouse_id": warehouse["id"], "earn_points": True,
        "lines": [{"product_id": product["id"], "qty": 1}], "payments": [{"method": "cash", "amount": 999_000}]})
    assert ok(sale, 201)["points_earned"] == 99 and sale.json()["points_balance"] == 99
    assert ok(pos.get(f"{API}/customers/{reseller['id']}"))["points"] == 99

    # Spending 50 points pays Rp 5,000; no points are earned on that part.
    spend = ok(pos.post(f"{API}/sales-orders", json={
        "external_id": "s2", "customer_id": reseller["id"], "warehouse_id": warehouse["id"], "earn_points": True,
        "lines": [{"product_id": product["id"], "qty": 1}],
        "payments": [{"method": "points", "amount": 5_000}, {"method": "cash", "amount": 994_000}]}), 201)
    assert spend["points_earned"] == 99 and spend["points_balance"] == 99 - 50 + 99
    too_many = pos.post(f"{API}/sales-orders", json={
        "external_id": "s3", "customer_id": reseller["id"], "warehouse_id": warehouse["id"],
        "lines": [{"product_id": product["id"], "qty": 1}],
        "payments": [{"method": "points", "amount": 999_000}]})
    assert too_many.status_code == 409 and "points" in too_many.json()["detail"]

    # Returning the first sale takes its 99 points back.
    ret = ok(pos.post(f"{API}/sales-returns", json={
        "external_id": "r1", "order_external_id": "s1", "lines": [{"product_id": product["id"], "qty": 1}],
        "refunds": [{"method": "cash", "amount": 999_000}]}), 201)
    assert ret["points_reversed"] == 99 and ret["points_balance"] == 49
    customer = next(c for c in ok(admin.get("/api/customers"))["items"] if c["code"] == "C2")
    assert customer["loyalty_points"] == 49


def test_promotions_are_managed_in_the_erp_and_listed_for_tills(app, admin, login):
    pos = integration_client(admin, app)
    sales = login("sales")
    promo = ok(sales.post("/api/promotions", json={"name": "Phone week", "kind": "price", "product_id": 1,
                                                   "value": 900_000, "ends_on": "2099-01-01"}), 201)
    assert promo["status"] == "running" and promo["product"]["sku"] == "PH-1"
    ok(sales.post("/api/promotions", json={"name": "Buy 2 get 1", "kind": "buy_get", "product_id": 2,
                                           "buy_qty": 2, "get_qty": 1}), 201)
    ok(sales.post("/api/promotions", json={"name": "Payday", "kind": "voucher", "value": 5, "code": "payday",
                                           "min_spend": 500_000}), 201)
    dup = sales.post("/api/promotions", json={"name": "Again", "kind": "voucher", "value": 5, "code": "PAYDAY"})
    assert dup.status_code == 409
    assert sales.post("/api/promotions", json={"name": "Bad", "kind": "price", "product_id": 1,
                                               "value": 2_000_000}).status_code == 422
    assert login("warehouse").post("/api/promotions", json={"name": "X", "kind": "percent",
                                                             "value": 5}).status_code == 403

    ok(sales.post("/api/promotions", json={"name": "Old", "kind": "percent", "value": 5, "ends_on": "2020-01-31"}), 201)
    ok(sales.put(f"/api/promotions/{promo['id']}", json={"name": "Phone week", "kind": "price", "product_id": 1,
                                                         "value": 950_000, "active": True}))
    listed = {p["name"]: p for p in ok(pos.get(f"{API}/promotions"))["items"]}
    assert set(listed) == {"Phone week", "Buy 2 get 1", "Payday"}  # ended ones drop out
    assert listed["Payday"]["code"] == "PAYDAY" and listed["Phone week"]["value"] == 950_000
    assert len(listed["Phone week"]["product_id"]) == 36


def test_stock_request_drafts_a_transfer_from_the_fullest_warehouse(app, admin):
    pos, warehouse, product, _ = setup(app, admin)  # 10 phones in Jakarta
    bandung = next(w for w in ok(pos.get(f"{API}/warehouses"))["items"] if w["code"] == "BDG")
    request = ok(pos.post(f"{API}/stock-requests", json={
        "warehouse_id": bandung["id"], "requested_by": "Putri", "note": "Weekend rush",
        "lines": [{"product_id": product["id"], "qty": 4}]}), 201)
    assert request["from"] == "Jakarta DC" and request["to"] == "Bandung Store" and request["status"] == "draft"
    transfer = ok(admin.get("/api/transfers"))["items"][0]
    assert transfer["number"] == request["number"]
    nothing = pos.post(f"{API}/stock-requests", json={"warehouse_id": warehouse["id"], "requested_by": "Putri",
                                                        "lines": [{"product_id": product["id"], "qty": 1}]})
    assert nothing.status_code == 409  # Bandung has none to send to Jakarta
