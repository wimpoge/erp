"""Login, sessions, role permissions and the integration API."""

from fastapi.testclient import TestClient

from conftest import PASSWORD, ok
from test_flows import buy, receive_all


def test_everything_needs_a_login(app):
    anonymous = TestClient(app)
    for path in ("/api/products", "/api/sales-orders", "/api/invoices", "/api/reports/dashboard", "/api/auth/me"):
        assert anonymous.get(path).status_code == 401, path


def test_login_cookie_and_logout(app):
    client = TestClient(app)
    r = client.post("/api/auth/login", json={"username": "Sales ", "password": PASSWORD})
    me = ok(r)
    assert me["username"] == "sales" and me["role"] == "sales" and "sales.write" in me["permissions"] and "settings.manage" not in me["permissions"]
    cookie = r.headers["set-cookie"]
    assert "erp_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_email_also_works_for_login(app):
    r = TestClient(app).post("/api/auth/login", json={"username": "Sales@Test.dev", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["username"] == "sales"


def test_wrong_password_unknown_user_and_lockout(app):
    client = TestClient(app)
    wrong = client.post("/api/auth/login", json={"username": "sales", "password": "nope"})
    unknown = client.post("/api/auth/login", json={"username": "ghost", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()
    for _ in range(4):
        client.post("/api/auth/login", json={"username": "sales", "password": "nope"})
    locked = client.post("/api/auth/login", json={"username": "sales", "password": PASSWORD})
    assert locked.status_code == 423


def test_roles_limit_what_people_can_do(login):
    sales, warehouse, accountant, purchasing = login("sales"), login("warehouse"), login("accountant"), login("purchasing")
    po_body = {"supplier_id": 1, "warehouse_id": 1, "lines": [{"product_id": 1, "qty": 1, "unit_cost": 1}]}
    so_body = {"customer_id": 1, "warehouse_id": 1, "lines": [{"product_id": 1, "qty": 1}]}

    assert sales.post("/api/purchase-orders", json=po_body).status_code == 403
    assert sales.post("/api/sales-orders", json=so_body).status_code == 201
    assert warehouse.post("/api/sales-orders", json=so_body).status_code == 403
    assert accountant.post("/api/products", json={"sku": "X", "name": "X", "sale_price": 1}).status_code == 403
    assert purchasing.get("/api/settings/users").status_code == 403

    # Purchasing orders, the warehouse receives.
    po = buy(purchasing, {1: (5, 100)})
    lines = {po["lines"][0]["id"]: 5}
    assert purchasing.post(f"/api/purchase-orders/{po['id']}/receive", json={"lines": lines}).status_code == 403
    assert warehouse.post(f"/api/purchase-orders/{po['id']}/receive", json={"lines": lines}).status_code == 200


def test_admin_manages_users(admin, app):
    new = ok(admin.post("/api/settings/users", json={"username": "budi", "email": "budi@test.dev", "full_name": "Budi",
                                                     "role": "warehouse", "password": "longenough"}), 201)
    assert admin.post("/api/settings/users", json={"username": "budi", "email": "other@test.dev", "full_name": "B", "role": "sales",
                                                   "password": "longenough"}).status_code == 409
    ok(admin.patch(f"/api/settings/users/{new['id']}", json={"active": False}))
    assert TestClient(app).post("/api/auth/login", json={"username": "budi",
                                                         "password": "longenough"}).status_code == 401
    me = ok(admin.get("/api/auth/me"))
    assert admin.patch(f"/api/settings/users/{me['id']}", json={"role": "sales"}).status_code == 422


# ---------------------------------------------------------------- integration API


def integration_client(admin, app) -> TestClient:
    created = ok(admin.post("/api/settings/api-clients", json={"name": "Store POS"}), 201)
    client = TestClient(app)
    token = ok(client.post("/api/integration/v1/token", json={
        "client_id": created["client_id"], "client_secret": created["client_secret"]}))
    client.headers["Authorization"] = f"Bearer {token['access_token']}"
    return client


def test_integration_token_is_required(app, admin):
    anonymous = TestClient(app)
    assert anonymous.get("/api/integration/v1/products").status_code == 401
    bad = anonymous.post("/api/integration/v1/token", json={"client_id": "cli_x", "client_secret": "nope"})
    assert bad.status_code == 401
    created = ok(admin.post("/api/settings/api-clients", json={"name": "Web shop"}), 201)
    assert len(created["client_secret"]) > 30
    assert "client_secret" not in ok(admin.get("/api/settings/api-clients"))[0]  # shown once only


def test_order_import_is_idempotent(app, admin):
    receive_all(admin, buy(admin, {1: (10, 600_000)}))
    pos = integration_client(admin, app)
    warehouse = ok(pos.get("/api/integration/v1/warehouses"))["items"][0]
    product = next(p for p in ok(pos.get("/api/integration/v1/products"))["items"] if p["sku"] == "PH-1")
    customer = ok(pos.get("/api/integration/v1/customers"))["items"][0]
    assert len(product["id"]) == 36  # public UUIDs only, never internal ids

    body = {"external_id": "pos-KG01-000123", "customer_id": customer["id"], "warehouse_id": warehouse["id"],
            "lines": [{"product_id": product["id"], "qty": 2}]}
    first = pos.post("/api/integration/v1/sales-orders", json=body)
    again = pos.post("/api/integration/v1/sales-orders", json=body)
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["number"] == again.json()["number"] and first.json()["status"] == "confirmed"
    orders = ok(admin.get("/api/sales-orders", params={"q": first.json()["number"]}))
    assert orders["total"] == 1 and orders["items"][0]["source"] == "api"

    stock = ok(pos.get(f"/api/integration/v1/warehouses/{warehouse['id']}/stock"))["items"]
    assert stock == [{"product_id": product["id"], "on_hand": 10}]  # confirmed, not shipped yet

    body["external_id"] = "pos-KG01-000124"
    body["lines"][0]["product_id"] = "00000000-0000-0000-0000-000000000000"
    assert pos.post("/api/integration/v1/sales-orders", json=body).status_code == 422


def till_sale(pos, external_id: str, customer: dict, warehouse: dict, product: dict, qty: int, payments: list[dict],
              **line) -> object:
    return pos.post("/api/integration/v1/sales-orders", json={
        "external_id": external_id, "customer_id": customer["id"], "warehouse_id": warehouse["id"],
        "reference": external_id, "lines": [{"product_id": product["id"], "qty": qty, **line}], "payments": payments})


def test_paid_till_sale_ships_invoices_and_settles(app, admin):
    receive_all(admin, buy(admin, {1: (10, 600_000)}))
    pos = integration_client(admin, app)
    settings = ok(pos.get("/api/integration/v1/settings"))
    assert settings["tax_rate"] == 11 and settings["currency"] == "IDR" and "paid_sales" in settings["features"]
    warehouse = ok(pos.get("/api/integration/v1/warehouses"))["items"][0]
    product = next(p for p in ok(pos.get("/api/integration/v1/products"))["items"] if p["sku"] == "PH-1")
    assert product["category"] == "Smartphone"
    reseller = next(c for c in ok(pos.get("/api/integration/v1/customers"))["items"] if c["code"] == "C2")
    assert reseller["discount_pct"] == 10 and reseller["group"] == "Reseller"

    # 6 x 1,000,000 less the reseller's 10% = 5,400,000 + 11% tax = 5,994,000: past the 5,000,000 credit
    # limit, but paid in full on the spot, so no credit is extended and it goes through.
    payments = [{"method": "cash", "amount": 994_000}, {"method": "card", "amount": 5_000_000, "reference": "APPR-1"}]
    sale = ok(till_sale(pos, "pos-1", reseller, warehouse, product, 6, payments), 201)
    assert sale["total"] == 5_994_000 and sale["status"] == "delivered" and sale["invoice_status"] == "paid"
    assert ok(till_sale(pos, "pos-1", reseller, warehouse, product, 6, payments))["number"] == sale["number"]
    stock = ok(pos.get(f"/api/integration/v1/warehouses/{warehouse['id']}/stock"))["items"]
    assert stock == [{"product_id": product["id"], "on_hand": 4}]
    invoice = ok(admin.get("/api/invoices", params={"q": sale["invoice_number"]}))["items"][0]
    assert invoice["total"] == invoice["amount_paid"] == 5_994_000

    # A line's own discount replaces the group's.
    full_price = ok(till_sale(pos, "pos-2", reseller, warehouse, product, 1, [{"method": "qris", "amount": 1_110_000}],
                              discount_pct=0), 201)
    assert full_price["total"] == 1_110_000


def test_refused_till_sale_leaves_nothing_behind(app, admin):
    receive_all(admin, buy(admin, {1: (2, 600_000)}))
    pos = integration_client(admin, app)
    warehouse = ok(pos.get("/api/integration/v1/warehouses"))["items"][0]
    product = next(p for p in ok(pos.get("/api/integration/v1/products"))["items"] if p["sku"] == "PH-1")
    walk_in = next(c for c in ok(pos.get("/api/integration/v1/customers"))["items"] if c["code"] == "C1")

    short = till_sale(pos, "pos-1", walk_in, warehouse, product, 1, [{"method": "cash", "amount": 1}])
    assert short.status_code == 422 and "add up to" in short.json()["detail"]
    too_many = till_sale(pos, "pos-2", walk_in, warehouse, product, 3, [{"method": "cash", "amount": 3_330_000}])
    assert too_many.status_code == 409 and "Not enough" in too_many.json()["detail"]
    bad_method = till_sale(pos, "pos-3", walk_in, warehouse, product, 1, [{"method": "barter", "amount": 1_110_000}])
    assert bad_method.status_code == 422
    assert ok(pos.get("/api/integration/v1/sales-orders"))["total"] == 0

    # The refused attempts did not use up order numbers, and a retry with the same id now works.
    sale = ok(till_sale(pos, "pos-2", walk_in, warehouse, product, 2, [{"method": "cash", "amount": 2_220_000}]), 201)
    assert sale["number"].endswith("-00001") and sale["invoice_status"] == "paid"


def test_till_creates_customers(app, admin):
    pos = integration_client(admin, app)
    created = ok(pos.post("/api/integration/v1/customers", json={"name": " Siti ", "phone": "0812"}), 201)
    assert created["name"] == "Siti" and created["discount_pct"] == 0 and len(created["id"]) == 36
    assert created["id"] in {c["id"] for c in ok(pos.get("/api/integration/v1/customers"))["items"]}
    assert pos.post("/api/integration/v1/customers", json={"name": "X", "email": "not-an-email"}).status_code == 422


def test_revoked_client_loses_access(app, admin):
    pos = integration_client(admin, app)
    client_row = ok(admin.get("/api/settings/api-clients"))[0]
    ok(admin.patch(f"/api/settings/api-clients/{client_row['id']}", json={"active": False}))
    assert pos.get("/api/integration/v1/products").status_code == 401


def test_cashiers_log_in_at_the_pos_not_the_erp(app, admin):
    erp_login = TestClient(app).post("/api/auth/login", json={"username": "cashier", "password": PASSWORD})
    assert erp_login.status_code == 403 and "Log in at the POS" in erp_login.json()["detail"]
    assert "pos.sell" not in ok(admin.get("/api/auth/me"))["permissions"]  # office roles don't sell

    pos = integration_client(admin, app)
    assert "cashier_login" in ok(pos.get("/api/integration/v1/settings"))["features"]
    cashier = ok(pos.post("/api/integration/v1/cashiers/login", json={"username": "Cashier ", "password": PASSWORD}))
    assert cashier == {"username": "cashier", "full_name": "Cashier", "email": "cashier@test.dev"}
    assert pos.post("/api/integration/v1/cashiers/login",
                    json={"username": "sales", "password": PASSWORD}).status_code == 403
    for _ in range(5):
        wrong = pos.post("/api/integration/v1/cashiers/login", json={"username": "cashier", "password": "nope"})
    assert wrong.status_code == 401
    assert pos.post("/api/integration/v1/cashiers/login",
                    json={"username": "cashier", "password": PASSWORD}).status_code == 423  # same lockout

    me = next(u for u in ok(admin.get("/api/settings/users")) if u["username"] == "cashier")
    ok(admin.patch(f"/api/settings/users/{me['id']}", json={"active": False}))
    assert pos.post("/api/integration/v1/cashiers/login",
                    json={"username": "cashier", "password": PASSWORD}).status_code == 401
    assert "cashier" in {r["name"] for r in ok(admin.get("/api/settings/roles"))}
