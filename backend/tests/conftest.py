import os

import pytest
from fastapi.testclient import TestClient

from erp.config import Settings
from erp.db import make_session_factory
from erp.main import create_app
from erp.models import Base, Category, Customer, CustomerGroup, Product, Supplier, User, Warehouse
from erp.services.auth import hash_password

PASSWORD = "password123"
ROLES = ("admin", "manager", "sales", "purchasing", "warehouse", "accountant")


@pytest.fixture
def db_factory(tmp_path):
    # SQLite by default; set ERP_TEST_DATABASE_URL to run the same tests on Postgres.
    url = os.environ.get("ERP_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'erp.db'}"
    factory = make_session_factory(url)
    engine = factory.kw["bind"]
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with factory() as db:
        for role in ROLES:
            db.add(User(username=role, email=f"{role}@test.dev", full_name=role.title(), role=role,
                        password_hash=hash_password(PASSWORD)))
        phones = Category(name="Smartphone")
        db.add_all([
            Warehouse(code="JKT", name="Jakarta DC", city="Jakarta"),
            Warehouse(code="BDG", name="Bandung Store", city="Bandung"),
            phones,
            Product(sku="PH-1", name="Phone One", category=phones, sale_price=1_000_000, reorder_point=5),
            Product(sku="PH-2", name="Phone Two", category=phones, sale_price=2_000_000, reorder_point=0),
            CustomerGroup(code="RETAIL", name="Retail", discount_pct=0),
            CustomerGroup(code="RESELLER", name="Reseller", discount_pct=10),
            Supplier(code="S1", name="Supplier One", payment_terms_days=30),
        ])
        db.flush()
        db.add_all([
            Customer(code="C1", name="Walk-in Buyer", group_id=1, payment_terms_days=14),
            Customer(code="C2", name="Reseller Co", group_id=2, payment_terms_days=30, credit_limit=5_000_000),
        ])
        db.commit()
    return factory


@pytest.fixture
def app(db_factory):
    # _env_file=None: a local backend/.env with production settings must not leak into tests.
    return create_app(db_factory, Settings(_env_file=None, database_url="sqlite://"))


@pytest.fixture
def login(app):
    clients = []

    def _login(role: str) -> TestClient:
        client = TestClient(app)
        r = client.post("/api/auth/login", json={"username": role, "password": PASSWORD})
        assert r.status_code == 200, r.text
        clients.append(client)
        return client

    yield _login
    for c in clients:
        c.close()


@pytest.fixture
def admin(login):
    return login("admin")


def ok(response, status: int = 200) -> dict:
    assert response.status_code == status, response.text
    return response.json()
