from sqlalchemy import delete, func, select

from erp_service.models import ApiToken
from erp_service.models import Customer as ErpCustomer
from erp_service.models import Product as ErpProduct
from pos_service.models import Customer, CustomerGroup, Location, Product, ProductStock, Register
from pos_service.sync import run_sync


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def events(http, run_id, action=None) -> list[dict]:
    return http.get(f"/api/sync/runs/{run_id}/events", params={"action": action} if action else {}).json()


def test_first_sync_mirrors_everything(pos_http, pos_db):
    run = pos_http.post("/api/sync").json()

    assert run["status"] == "ok"
    with pos_db() as db:
        assert count(db, Location) == 2
        assert count(db, Register) == 4
        assert count(db, CustomerGroup) == 3
        assert count(db, Customer) == 10
        assert count(db, Product) == 15
        assert count(db, ProductStock) == 30  # 15 products x 2 stores, read in pages of 4
        # POS numbers its own rows; the ERP link is the public UUID.
        assert {loc.id for loc in db.scalars(select(Location))} == {1, 2}
    assert run["summary"]["products"]["inserted"] == 15
    assert len(events(pos_http, run["id"], "insert")) == 3 + 2 + 4 + 10 + 15 + 30


def test_second_sync_without_changes_writes_nothing(pos_http):
    pos_http.post("/api/sync")
    run = pos_http.post("/api/sync").json()
    assert run["status"] == "ok"
    assert events(pos_http, run["id"]) == []


def test_changes_in_the_erp_are_updated_and_removals_deactivated(pos_http, pos_db, erp_db):
    pos_http.post("/api/sync")
    with erp_db() as db:
        changed = db.scalars(select(ErpProduct).order_by(ErpProduct.id)).first()
        changed.price += 5000
        gone = db.scalars(select(ErpCustomer).order_by(ErpCustomer.id)).first()
        db.delete(gone)
        db.commit()
        changed_id, gone_id = str(changed.public_id), str(gone.public_id)

    run = pos_http.post("/api/sync").json()

    updates = events(pos_http, run["id"], "update")
    assert [(e["table"], e["erp_public_id"], e["message"]) for e in updates] == [
        ("products", changed_id, "changed: price")
    ]
    assert [e["erp_public_id"] for e in events(pos_http, run["id"], "deactivate")] == [gone_id]
    with pos_db() as db:
        customer = db.scalar(select(Customer).where(Customer.erp_public_id == gone.public_id))
        assert customer is not None and customer.active is False  # kept: orders may point at it


def test_an_empty_answer_never_empties_a_table(pos_http, pos_db, erp):
    pos_http.post("/api/sync")
    real_list_all = erp.list_all
    erp.list_all = lambda path, page_size=4: [] if path == "/api/customer-groups" else real_list_all(path)

    run = pos_http.post("/api/sync").json()

    assert run["status"] == "ok"
    assert run["summary"]["customer_groups"]["skipped"] is True
    assert "kept 3 existing rows" in events(pos_http, run["id"], "skipped")[0]["message"]
    with pos_db() as db:
        assert db.scalar(select(func.count()).select_from(CustomerGroup).where(CustomerGroup.active)) == 3


def test_a_bad_row_is_logged_and_the_rest_still_syncs(pos_http, pos_db, erp):
    real_list_all = erp.list_all

    def list_all(path, page_size=4):
        rows = real_list_all(path)
        if path == "/api/products":
            del rows[0]["price"]  # e.g. the ERP renamed a field
        return rows

    erp.list_all = list_all
    run = pos_http.post("/api/sync").json()

    assert run["status"] == "partial"
    assert run["summary"]["products"]["errors"] == 1
    assert run["summary"]["products"]["inserted"] == 14
    errors = events(pos_http, run["id"], "error")
    assert errors[0]["table"] == "products" and "price" in errors[0]["message"]
    # Its stock rows can't be linked either, in both stores, and say why.
    assert [e["table"] for e in errors[1:]] == ["stock:KG01", "stock:KG02"]
    assert all("unknown product" in e["message"] for e in errors[1:])
    state = {s["key"]: s["last_status"] for s in pos_http.get("/api/sync/state").json()}
    assert state["products"] == "partial" and state["customers"] == "ok"


def test_erp_down_fails_the_step_not_the_run(pos_http, erp):
    real_list_all = erp.list_all

    def list_all(path, page_size=4):
        if path == "/api/customers":
            raise ConnectionError("ERP unreachable")
        return real_list_all(path)

    erp.list_all = list_all
    run = pos_http.post("/api/sync").json()
    assert run["status"] == "partial"
    assert "error" in run["summary"]["customers"]
    assert run["summary"]["products"]["inserted"] == 15


def test_revoked_token_is_renewed_transparently(pos_db, erp, erp_db):
    erp.request("GET", "/api/stores")
    old_token = erp._token
    with erp_db() as db:
        db.execute(delete(ApiToken))
        db.commit()

    with pos_db() as db:
        assert run_sync(db, erp).status == "ok"
    assert erp._token != old_token
