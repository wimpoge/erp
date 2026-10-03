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


def test_revoked_client_loses_access(app, admin):
    pos = integration_client(admin, app)
    client_row = ok(admin.get("/api/settings/api-clients"))[0]
    ok(admin.patch(f"/api/settings/api-clients/{client_row['id']}", json={"active": False}))
    assert pos.get("/api/integration/v1/products").status_code == 401
