"""End-to-end business flows through the HTTP API."""

from datetime import date, timedelta

from conftest import ok


def buy(client, qty_by_product: dict[int, tuple[int, int]], warehouse_id: int = 1) -> dict:
    """Create and confirm a purchase order: {product_id: (qty, unit_cost)}."""
    po = ok(client.post("/api/purchase-orders", json={
        "supplier_id": 1, "warehouse_id": warehouse_id,
        "lines": [{"product_id": p, "qty": q, "unit_cost": c} for p, (q, c) in qty_by_product.items()],
    }), 201)
    return ok(client.post(f"/api/purchase-orders/{po['id']}/confirm"))


def receive_all(client, po: dict) -> dict:
    lines = {li["id"]: li["qty"] - li["qty_received"] for li in po["lines"]}
    return ok(client.post(f"/api/purchase-orders/{po['id']}/receive", json={"lines": lines}))


def stock_of(client, product_id: int, warehouse_id: int = 1) -> dict:
    product = ok(client.get(f"/api/products/{product_id}"))
    return next(w for w in product["warehouses"] if w["warehouse"]["id"] == warehouse_id)


# ---------------------------------------------------------------- purchasing


def test_purchase_to_pay(admin):
    po = buy(admin, {1: (10, 600_000), 2: (4, 1_500_000)})
    assert po["status"] == "confirmed" and po["number"].startswith("PO-")
    assert po["subtotal"] == 12_000_000 and po["tax"] == 1_320_000 and po["total"] == 13_320_000
    assert stock_of(admin, 1)["incoming"] == 10

    # Partial receipt: stock and average cost follow, status moves on.
    po = ok(admin.post(f"/api/purchase-orders/{po['id']}/receive", json={"lines": {po["lines"][0]["id"]: 6}}))
    assert po["status"] == "partially_received"
    assert stock_of(admin, 1) | {"warehouse": None} == {"warehouse": None, "on_hand": 6, "reserved": 0,
                                                       "available": 6, "incoming": 4}
    assert ok(admin.get("/api/products/1"))["avg_cost"] == 600_000

    # Can't receive more than was ordered.
    over = admin.post(f"/api/purchase-orders/{po['id']}/receive", json={"lines": {po["lines"][0]["id"]: 5}})
    assert over.status_code == 422

    po = receive_all(admin, po)
    assert po["status"] == "received" and len(po["receipts"]) == 2

    bill_ref = ok(admin.post(f"/api/purchase-orders/{po['id']}/bill", json={"supplier_ref": "SUP-INV-9"}))
    bill = ok(admin.get(f"/api/invoices/{bill_ref['id']}"))
    assert bill["kind"] == "supplier" and bill["total"] == 13_320_000 and bill["partner_ref"] == "SUP-INV-9"
    assert ok(admin.get(f"/api/purchase-orders/{po['id']}"))["billing_status"] == "billed"
    # Everything received is billed: a second bill is refused.
    assert admin.post(f"/api/purchase-orders/{po['id']}/bill", json={}).status_code == 409

    bill = ok(admin.post(f"/api/invoices/{bill['id']}/payments", json={"amount": 13_320_000}), 201)
    assert bill["status"] == "paid" and bill["payments"][0]["number"].startswith("PAY-")


def test_moving_average_cost(admin):
    receive_all(admin, buy(admin, {1: (10, 500_000)}))
    receive_all(admin, buy(admin, {1: (30, 700_000)}))
    # (10 * 500k + 30 * 700k) / 40
    assert ok(admin.get("/api/products/1"))["avg_cost"] == 650_000


def test_confirmed_orders_are_locked(admin):
    po = buy(admin, {1: (1, 100)})
    edit = admin.put(f"/api/purchase-orders/{po['id']}", json={
        "supplier_id": 1, "warehouse_id": 1, "lines": [{"product_id": 1, "qty": 2, "unit_cost": 100}]})
    assert edit.status_code == 409
    receive_all(admin, po)
    assert admin.post(f"/api/purchase-orders/{po['id']}/cancel").status_code == 409


# ---------------------------------------------------------------- sales


def sell(client, customer_id: int, lines: list[dict], warehouse_id: int = 1) -> dict:
    return ok(client.post("/api/sales-orders", json={"customer_id": customer_id, "warehouse_id": warehouse_id,
                                                     "lines": lines}), 201)


def test_order_to_cash(admin):
    receive_all(admin, buy(admin, {1: (10, 600_000)}))

    # Reseller group: 10% off by default.
    so = sell(admin, 2, [{"product_id": 1, "qty": 4}])
    assert so["lines"][0]["discount_pct"] == 10 and so["lines"][0]["unit_price"] == 1_000_000
    assert so["subtotal"] == 3_600_000 and so["discount"] == 400_000 and so["total"] == 3_996_000
    so = ok(admin.post(f"/api/sales-orders/{so['id']}/confirm"))
    assert stock_of(admin, 1) | {"warehouse": None} == {"warehouse": None, "on_hand": 10, "reserved": 4,
                                                       "available": 6, "incoming": 0}

    so = ok(admin.post(f"/api/sales-orders/{so['id']}/deliver", json={"lines": {so["lines"][0]["id"]: 3}}))
    assert so["status"] == "partially_delivered" and stock_of(admin, 1)["on_hand"] == 7
    assert stock_of(admin, 1)["reserved"] == 1

    inv_ref = ok(admin.post(f"/api/sales-orders/{so['id']}/invoice", json={}))
    invoice = ok(admin.get(f"/api/invoices/{inv_ref['id']}"))
    assert invoice["total"] == 2_997_000 and invoice["status"] == "open"  # 3 x 900k + 11%
    assert invoice["due_date"] == str(date.today() + timedelta(days=30))

    invoice = ok(admin.post(f"/api/invoices/{invoice['id']}/payments",
                            json={"amount": 1_000_000, "method": "bank_transfer"}), 201)
    assert invoice["status"] == "partially_paid" and invoice["balance"] == 1_997_000
    too_much = admin.post(f"/api/invoices/{invoice['id']}/payments", json={"amount": 1_997_001})
    assert too_much.status_code == 422
    invoice = ok(admin.post(f"/api/invoices/{invoice['id']}/payments", json={"amount": 1_997_000}), 201)
    assert invoice["status"] == "paid"
    assert invoice["activity"][-1]["message"].endswith("Rp 1.997.000 received by bank transfer")
    assert ", Rp 1.997.000" in invoice["activity"][-1]["message"]

    so = ok(admin.get(f"/api/sales-orders/{so['id']}"))
    assert so["invoice_status"] == "partially_invoiced"
    assert [a["action"] for a in so["activity"]] == ["created", "confirmed", "delivered", "invoiced"]


def test_cannot_ship_stock_that_is_not_there(admin):
    receive_all(admin, buy(admin, {1: (2, 600_000)}))
    so = sell(admin, 1, [{"product_id": 1, "qty": 5}])
    so = ok(admin.post(f"/api/sales-orders/{so['id']}/confirm"))
    r = admin.post(f"/api/sales-orders/{so['id']}/deliver", json={"lines": {so["lines"][0]["id"]: 5}})
    assert r.status_code == 409 and "2 on hand, 5 needed" in r.json()["detail"]
    # Nothing was half-written.
    assert stock_of(admin, 1)["on_hand"] == 2
    assert ok(admin.get(f"/api/sales-orders/{so['id']}"))["deliveries"] == []


def test_credit_limit_blocks_confirmation(admin):
    receive_all(admin, buy(admin, {2: (5, 1_500_000)}))
    first = sell(admin, 2, [{"product_id": 2, "qty": 2}])  # 2 x 1.8m + tax = 3,996,000
    ok(admin.post(f"/api/sales-orders/{first['id']}/confirm"))
    second = sell(admin, 2, [{"product_id": 2, "qty": 1}])  # 1,998,000 more passes the 5m limit
    r = admin.post(f"/api/sales-orders/{second['id']}/confirm")
    assert r.status_code == 409 and "Credit limit exceeded" in r.json()["detail"]
    assert "limit Rp 5.000.000, already open Rp 3.996.000, this order Rp 1.998.000." in r.json()["detail"]


def test_cancelling_an_invoice_frees_its_quantities(admin):
    receive_all(admin, buy(admin, {1: (5, 600_000)}))
    so = ok(admin.post(f"/api/sales-orders/{sell(admin, 1, [{'product_id': 1, 'qty': 2}])['id']}/confirm"))
    ok(admin.post(f"/api/sales-orders/{so['id']}/deliver", json={"lines": {so["lines"][0]["id"]: 2}}))
    inv = ok(admin.post(f"/api/sales-orders/{so['id']}/invoice", json={}))
    ok(admin.post(f"/api/invoices/{inv['id']}/cancel"))
    assert ok(admin.get(f"/api/sales-orders/{so['id']}"))["invoice_status"] == "not_invoiced"
    again = ok(admin.post(f"/api/sales-orders/{so['id']}/invoice", json={}))
    assert again["number"] != inv["number"]


def test_overdue_invoices_show_up(admin):
    receive_all(admin, buy(admin, {1: (5, 600_000)}))
    so = ok(admin.post(f"/api/sales-orders/{sell(admin, 1, [{'product_id': 1, 'qty': 1}])['id']}/confirm"))
    ok(admin.post(f"/api/sales-orders/{so['id']}/deliver", json={"lines": {so["lines"][0]["id"]: 1}}))
    long_ago = str(date.today() - timedelta(days=40))
    ok(admin.post(f"/api/sales-orders/{so['id']}/invoice", json={"invoice_date": long_ago}))  # 14-day terms

    overdue = ok(admin.get("/api/invoices", params={"kind": "customer", "status": "overdue"}))
    assert overdue["total"] == 1 and overdue["items"][0]["status"] == "overdue"
    assert overdue["items"][0]["days_overdue"] == 26
    aging = ok(admin.get("/api/reports/aging", params={"kind": "customer"}))
    assert aging["totals"]["1-30"] == 1_110_000


# ---------------------------------------------------------------- inventory


def test_transfer_and_stock_count(admin):
    receive_all(admin, buy(admin, {1: (10, 600_000)}))
    tr = ok(admin.post("/api/transfers", json={"from_warehouse_id": 1, "to_warehouse_id": 2,
                                               "lines": [{"product_id": 1, "qty": 4}]}), 201)
    assert tr["status"] == "draft" and stock_of(admin, 1, 2)["on_hand"] == 0
    tr = ok(admin.post(f"/api/transfers/{tr['id']}/validate"))
    assert tr["status"] == "done"
    assert (stock_of(admin, 1, 1)["on_hand"], stock_of(admin, 1, 2)["on_hand"]) == (6, 4)

    too_many = ok(admin.post("/api/transfers", json={"from_warehouse_id": 2, "to_warehouse_id": 1,
                                                     "lines": [{"product_id": 1, "qty": 9}]}), 201)
    assert admin.post(f"/api/transfers/{too_many['id']}/validate").status_code == 409

    count = ok(admin.post("/api/adjustments", json={"warehouse_id": 2, "reason": "Monthly count",
                                                    "lines": [{"product_id": 1, "counted_qty": 3}]}), 201)
    assert count["lines"][0]["difference"] == -1
    count = ok(admin.post(f"/api/adjustments/{count['id']}/validate"))
    assert count["lines"][0]["system_qty"] == 4 and stock_of(admin, 1, 2)["on_hand"] == 3

    moves = ok(admin.get("/api/stock-moves", params={"product_id": 1}))
    assert [m["kind"] for m in moves["items"]] == ["adjustment", "transfer_in", "transfer_out", "receipt"]
    assert sum(m["qty"] for m in moves["items"]) == 9  # ledger adds up to stock on hand


def test_document_numbers_are_sequential(admin):
    numbers = [buy(admin, {1: (1, 100)})["number"] for _ in range(3)]
    year = date.today().year
    assert numbers == [f"PO-{year}-00001", f"PO-{year}-00002", f"PO-{year}-00003"]


def test_low_stock_and_dashboard(admin):
    receive_all(admin, buy(admin, {1: (3, 600_000), 2: (2, 1_500_000)}))
    low = ok(admin.get("/api/products", params={"low_stock": True}))
    assert [p["sku"] for p in low["items"]] == ["PH-1"]  # 3 on hand, reorder point 5

    so = ok(admin.post(f"/api/sales-orders/{sell(admin, 1, [{'product_id': 2, 'qty': 1}])['id']}/confirm"))
    ok(admin.post(f"/api/sales-orders/{so['id']}/deliver", json={"lines": {so["lines"][0]["id"]: 1}}))
    ok(admin.post(f"/api/sales-orders/{so['id']}/invoice", json={}))
    dash = ok(admin.get("/api/reports/dashboard"))
    assert dash["revenue_30d"] == 2_000_000
    assert dash["gross_profit_30d"] == 500_000
    assert dash["stock_value"] == 3 * 600_000 + 1 * 1_500_000
    assert dash["receivables"]["amount"] == 2_220_000
    assert dash["monthly"][-1]["revenue"] == 2_000_000 and len(dash["monthly"]) == 12


# ---------------------------------------------------------------- lists


def test_list_search_sort_and_paging(admin):
    for _ in range(3):
        buy(admin, {1: (1, 100)})
    page = ok(admin.get("/api/purchase-orders", params={"page_size": 2, "sort": "number"}))
    assert page["total"] == 3 and len(page["items"]) == 2
    assert page["items"][0]["number"] < page["items"][1]["number"]
    found = ok(admin.get("/api/products", params={"q": "two"}))
    assert [p["sku"] for p in found["items"]] == ["PH-2"]
