"""Shared fixtures: a seeded mock ERP and a POS wired to it, both in-process on SQLite files.

The POS talks to the ERP through FastAPI's TestClient (an httpx.Client), so tests go
through the real HTTP contract: tokens, pagination, status codes and JSON shapes.
"""

import pytest
from fastapi.testclient import TestClient

from erp_service import models as erp_models
from erp_service.config import Settings as ErpSettings
from erp_service.db import make_session_factory as erp_session_factory
from erp_service.main import create_app as create_erp_app
from erp_service.seed import seed
from pos_service import models as pos_models
from pos_service.auth import hash_password
from pos_service.config import Settings as PosSettings
from pos_service.db import make_session_factory as pos_session_factory
from pos_service.erp_client import ErpClient
from pos_service.main import create_app as create_pos_app


@pytest.fixture
def erp_db(tmp_path):
    factory = erp_session_factory(f"sqlite:///{tmp_path / 'erp.db'}")
    erp_models.Base.metadata.create_all(factory.kw["bind"])
    with factory() as db:
        seed(db, stores=2, products=15, customers=10, seed_value=1)
    return factory


@pytest.fixture
def erp_http(erp_db):
    with TestClient(create_erp_app(erp_db, ErpSettings())) as client:
        yield client


@pytest.fixture
def erp(erp_http):
    # Small pages so every sync exercises pagination.
    client = ErpClient(erp_http, "pos-dev", "pos-dev-secret", "POS")
    original = client.list_all
    client.list_all = lambda path, page_size=4: original(path, page_size)
    return client


@pytest.fixture
def pos_db(tmp_path):
    factory = pos_session_factory(f"sqlite:///{tmp_path / 'pos.db'}")
    pos_models.Base.metadata.create_all(factory.kw["bind"])
    with factory() as db:
        db.add(pos_models.User(username="admin", full_name="Admin", password_hash=hash_password("admin123"),
                               role="admin"))
        db.commit()
    return factory


@pytest.fixture
def pos_app(pos_db, erp):
    return create_pos_app(pos_db, erp, PosSettings())


def login(app, username: str, password: str) -> TestClient:
    client = TestClient(app)
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def pos_http(pos_app):
    """Logged in as an admin (no store of their own)."""
    with login(pos_app, "admin", "admin123") as client:
        yield client


@pytest.fixture
def synced_pos(pos_http):
    assert pos_http.post("/api/sync").json()["status"] == "ok"
    return pos_http


@pytest.fixture
def cashier_http(synced_pos, pos_app, pos_db):
    """Logged in as a cashier of store KG01 (location id 1)."""
    with pos_db() as db:
        db.add(pos_models.User(username="kasir1", full_name="Kasir Satu", password_hash=hash_password("kasir123"),
                               role="cashier", location_id=1))
        db.commit()
    with login(pos_app, "kasir1", "kasir123") as client:
        yield client
