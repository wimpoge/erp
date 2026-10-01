from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from pos_service.auth import hash_password, verify_password
from pos_service.models import StaffSession, User


def test_password_hashes_are_salted_and_verify():
    a, b = hash_password("kasir123"), hash_password("kasir123")
    assert a != b and a.startswith("scrypt$")
    assert verify_password("kasir123", a) and not verify_password("kasir124", a)


def test_everything_needs_a_login(pos_app):
    anonymous = TestClient(pos_app)
    for path in ("/api/locations", "/api/orders", "/api/customers", "/api/auth/me", "/api/sync/runs"):
        assert anonymous.get(path).status_code == 401, path


def test_login_sets_an_httponly_cookie_and_logout_ends_the_session(pos_app, pos_db):
    client = TestClient(pos_app)
    r = client.post("/api/auth/login", json={"username": "ADMIN ", "password": "admin123"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    cookie = r.headers["set-cookie"]
    assert "pos_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert client.get("/api/auth/me").json()["username"] == "admin"
    with pos_db() as db:  # only a hash of the cookie is stored
        assert db.scalar(select(StaffSession.token_hash)) != client.cookies["pos_session"]

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_wrong_password_and_unknown_user_look_the_same(pos_app):
    client = TestClient(pos_app)
    wrong = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    unknown = client.post("/api/auth/login", json={"username": "ghost", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Wrong username or password."}


def test_five_wrong_passwords_lock_the_account(pos_app, pos_db):
    client = TestClient(pos_app)
    for _ in range(5):
        client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 423 and "Try again" in r.json()["detail"]


def test_expired_session_is_rejected(pos_http, pos_db):
    with pos_db() as db:
        db.query(StaffSession).update({StaffSession.expires_at: datetime.now(UTC).replace(tzinfo=None) - timedelta(1)})
        db.commit()
    assert pos_http.get("/api/auth/me").status_code == 401


def test_cashier_works_only_in_their_own_store(cashier_http):
    me = cashier_http.get("/api/auth/me").json()
    assert me["role"] == "cashier" and me["location"]["code"] == "KG01"
    assert [loc["code"] for loc in cashier_http.get("/api/locations").json()] == ["KG01"]
    assert cashier_http.get("/api/products", params={"location_id": 2}).status_code == 403
    sale = {"location_id": 2, "lines": [{"product_id": 1, "qty": 1}], "payments": [{"method": "cash", "amount": 10**8}]}
    assert cashier_http.post("/api/orders", json=sale).status_code == 403


def test_sales_record_the_cashier_and_history_is_per_store(cashier_http, synced_pos):
    product = next(p for p in cashier_http.get("/api/products", params={"location_id": 1}).json() if p["on_hand"])
    sale = {"location_id": 1, "lines": [{"product_id": product["id"], "qty": 1}],
            "payments": [{"method": "cash", "amount": product["price"] + 2000}]}
    order = cashier_http.post("/api/orders", json=sale).json()
    assert order["cashier"] == "Kasir Satu"

    # An admin sale in another store is not in this cashier's history.
    other = next(p for p in synced_pos.get("/api/products", params={"location_id": 2}).json() if p["on_hand"])
    synced_pos.post("/api/orders", json={**sale, "location_id": 2, "lines": [{"product_id": other["id"], "qty": 1}],
                                         "payments": [{"method": "card", "amount": other["price"]}]})
    assert [o["id"] for o in cashier_http.get("/api/orders").json()] == [order["id"]]
    since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    summary = cashier_http.get("/api/orders/summary", params={"since": since}).json()
    # Cash in the drawer is what was paid minus the change given back.
    assert summary == {"count": 1, "revenue": product["price"], "by_method": {"cash": product["price"]}}


def test_back_office_is_admin_only(cashier_http):
    assert cashier_http.post("/api/sync").status_code == 403
    assert cashier_http.post("/api/orders/push-pending").status_code == 403
    assert cashier_http.get("/api/users").status_code == 403


def test_admin_manages_staff(synced_pos, pos_app, pos_db):
    r = synced_pos.post("/api/users", json={"username": "Budi", "full_name": "Budi Santoso", "password": "rahasia1",
                                             "location_id": 2})
    assert r.status_code == 201 and r.json()["username"] == "budi"
    assert synced_pos.post("/api/users", json={"username": "x1x", "full_name": "No store", "password": "rahasia1"}
                           ).status_code == 422  # a cashier needs a store
    budi = r.json()["id"]

    synced_pos.patch(f"/api/users/{budi}", json={"active": False})
    blocked = TestClient(pos_app).post("/api/auth/login", json={"username": "budi", "password": "rahasia1"})
    assert blocked.status_code == 401

    synced_pos.patch(f"/api/users/{budi}", json={"active": True, "password": "baru1234"})
    ok = TestClient(pos_app).post("/api/auth/login", json={"username": "budi", "password": "baru1234"})
    assert ok.status_code == 200

    me = synced_pos.get("/api/auth/me").json()
    assert synced_pos.patch(f"/api/users/{me['id']}", json={"active": False}).status_code == 422
    with pos_db() as db:
        assert db.scalar(select(User).filter_by(username="budi")).location_id == 2
