"""Demo company with a year of history, generated through the real business services.

Everything (stock, average costs, invoices, payments) comes from the same code paths the
API uses, so the numbers on every screen agree with each other. Deterministic per seed.
"""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from faker import Faker
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Category,
    Customer,
    CustomerGroup,
    Invoice,
    Product,
    PurchaseOrder,
    SalesOrder,
    StockLevel,
    Supplier,
    User,
    Warehouse,
    today,
)
from .services import finance, inventory, purchasing, sales
from .services.auth import hash_password
from .services.common import DomainError, set_setting

DEMO_PASSWORD = "demo1234"
DEMO_USERS = [
    ("admin@example.com", "Rafli Pratama", "admin"),
    ("manager@example.com", "Dewi Lestari", "manager"),
    ("sales@example.com", "Andi Wijaya", "sales"),
    ("purchasing@example.com", "Sari Utami", "purchasing"),
    ("warehouse@example.com", "Budi Santoso", "warehouse"),
    ("finance@example.com", "Rina Kurniawati", "accountant"),
]

WAREHOUSES = [
    ("JKT-DC", "Jakarta Distribution Center", "Jakarta", "Jl. Cakung Cilincing Km 3"),
    ("BDG-01", "Bandung Store", "Bandung", "Jl. Dago No. 88"),
    ("SBY-01", "Surabaya Store", "Surabaya", "Jl. Tunjungan No. 12"),
    ("PDG-01", "Padang Store", "Padang", "Jl. Khatib Sulaiman No. 5"),
]

# category -> (brands, price range, margin range, reorder point = company-wide minimum stock)
CATALOG = {
    "Smartphones": (["Samsung", "Xiaomi", "Oppo", "Vivo", "Realme"], (1_800_000, 14_000_000), (0.08, 0.15), 5),
    "Tablets": (["Samsung", "Xiaomi", "Lenovo"], (2_500_000, 9_000_000), (0.08, 0.14), 3),
    "Earbuds & Audio": (["JBL", "Soundcore", "Sony", "QCY"], (150_000, 2_500_000), (0.20, 0.35), 8),
    "Chargers": (["Anker", "Baseus", "Ugreen"], (80_000, 600_000), (0.30, 0.45), 10),
    "Cables": (["Anker", "Baseus", "Ugreen"], (35_000, 200_000), (0.35, 0.55), 12),
    "Cases & Protection": (["Spigen", "Nillkin", "UAG"], (60_000, 450_000), (0.40, 0.60), 10),
    "Power Banks": (["Anker", "Xiaomi", "Baseus"], (180_000, 900_000), (0.20, 0.30), 8),
    "Smartwatches": (["Xiaomi", "Huawei", "Amazfit"], (500_000, 4_000_000), (0.15, 0.25), 4),
}
VARIANTS = ["Lite", "Pro", "Max", "Plus", "Neo", "Air", "Ultra", "Mini", "SE", "Prime"]


def _product_name(rng: random.Random, category: str, brand: str) -> str:
    v = rng.choice(VARIANTS)
    if category in ("Smartphones", "Tablets"):
        return f"{brand} {rng.choice('ACGKMNRXZ')}{rng.randint(10, 99)} {v} {rng.choice([128, 256, 512])}GB"
    if category == "Chargers":
        return f"{brand} GaN Charger {rng.choice([20, 33, 45, 65, 100])}W {v}"
    if category == "Cables":
        return f"{brand} USB-C to {rng.choice(['USB-C', 'Lightning', 'USB-A'])} Cable {rng.choice([1, 1.5, 2])}m"
    if category == "Power Banks":
        return f"{brand} Power Bank {rng.choice([10_000, 20_000, 25_000])}mAh {v}"
    if category == "Smartwatches":
        return f"{brand} Watch {rng.randint(2, 9)} {v}"
    if category == "Earbuds & Audio":
        return f"{brand} {rng.choice(['Buds', 'Earbuds', 'Headphones', 'Speaker'])} {v} {rng.randint(1, 9)}"
    return f"{brand} {rng.choice(['Rugged', 'Clear', 'Slim', 'Leather'])} Case {v}"


def _round_price(value: float) -> int:
    step = 1_000 if value < 1_000_000 else 10_000
    return max(step, int(round(value / step)) * step - (1_000 if value >= 100_000 else 0))


@dataclass
class World:
    db: Session
    rng: random.Random
    users: dict[str, User]
    warehouses: list[Warehouse]
    products: list[Product]
    customers: list[Customer]
    suppliers: list[Supplier]
    agenda: dict[date, list] = field(default_factory=dict)
    backordered: set[int] = field(default_factory=set)

    def later(self, on: date, action) -> None:
        if on <= today():
            self.agenda.setdefault(on, []).append(action)


def seed(db: Session, *, months: int = 12, seed_value: int = 7) -> dict:
    rng = random.Random(seed_value)
    fake = Faker("id_ID")
    fake.seed_instance(seed_value)

    users = {}
    for email, name, role in DEMO_USERS:
        users[role] = User(email=email, full_name=name, role=role, password_hash=hash_password(DEMO_PASSWORD))
        db.add(users[role])
    set_setting(db, "company_name", "Kios Gawai Nusantara")
    set_setting(db, "company_address", "Jl. Jend. Sudirman Kav. 21, Jakarta Selatan 12920")
    set_setting(db, "company_phone", "+62 21 5550 1234")
    set_setting(db, "company_email", "finance@kiosgawai.example")
    set_setting(db, "company_tax_id", "01.234.567.8-012.000")
    set_setting(db, "bank_name", "Bank Central Asia (BCA)")
    set_setting(db, "bank_account", "123 456 7890")
    set_setting(db, "bank_holder", "PT Kios Gawai Nusantara")
    set_setting(db, "tax_rate", 11)

    warehouses = [Warehouse(code=c, name=n, city=city, address=a) for c, n, city, a in WAREHOUSES]
    db.add_all(warehouses)

    products = []
    names: set[str] = set()
    for category_name, (brands, (low, high), (m_low, m_high), reorder) in CATALOG.items():
        category = Category(name=category_name)
        db.add(category)
        for _ in range(rng.randint(12, 18)):
            brand = rng.choice(brands)
            name = _product_name(rng, category_name, brand)
            while name in names:  # every product name is unique, as in a real catalogue
                name = _product_name(rng, category_name, brand)
            names.add(name)
            price = _round_price(rng.uniform(low, high))
            products.append(Product(
                sku=f"{category_name[:3].upper()}-{len(products) + 1:04d}", name=name,
                category=category, brand=brand, barcode=fake.unique.ean13(), sale_price=price,
                avg_cost=int(price * (1 - rng.uniform(m_low, m_high))), reorder_point=reorder,
            ))
    products[-1].active = False  # one discontinued product
    db.add_all(products)

    groups = [CustomerGroup(code="RETAIL", name="Retail", discount_pct=0),
              CustomerGroup(code="MEMBER", name="Member", discount_pct=3),
              CustomerGroup(code="RESELLER", name="Reseller", discount_pct=8),
              CustomerGroup(code="CORPORATE", name="Corporate", discount_pct=5)]
    db.add_all(groups)
    customers = []
    for n in range(1, 71):
        group = rng.choices(groups, weights=[35, 30, 20, 15])[0]
        company = group.code in ("RESELLER", "CORPORATE")
        customers.append(Customer(
            code=f"C-{n:04d}", name=fake.company() if company else fake.name(), email=fake.email(),
            phone=fake.phone_number(), address=fake.street_address(), city=rng.choice([w.city for w in warehouses]),
            group=group, payment_terms_days=rng.choice([14, 30, 45]) if company else 7,
            credit_limit=rng.choice([50_000_000, 100_000_000, 150_000_000]) if company else 0,
        ))
    db.add_all(customers)
    suppliers = [Supplier(code=f"S-{n:03d}", name=f"PT {fake.last_name()} {rng.choice(['Elektronik', 'Teknologi', 'Distribusi', 'Gadget'])} Indonesia",
                          email=fake.company_email(), phone=fake.phone_number(), address=fake.street_address(),
                          city=rng.choice(["Jakarta", "Tangerang", "Surabaya", "Batam"]),
                          payment_terms_days=rng.choice([30, 45, 60])) for n in range(1, 13)]
    db.add_all(suppliers)
    db.commit()

    w = World(db, rng, users, warehouses, [p for p in products if p.active], customers, suppliers)
    w.backordered = {p.id for p in rng.sample(w.products, 8)}
    start = today() - timedelta(days=months * 30)
    _opening_stock(w, start)
    day = start + timedelta(days=1)
    while day <= today():
        _run_agenda(w, day)
        if day.weekday() < 6:  # the business is closed on Sundays
            _daily_business(w, day)
        _run_agenda(w, day)  # same-day follow-ups, e.g. an invoice paid the day it is issued
        db.commit()
        day += timedelta(days=1)
    _work_in_progress(w)
    db.commit()
    return {"users": [u[0] for u in DEMO_USERS], "password": DEMO_PASSWORD}


def _run_agenda(w: World, day: date) -> None:
    while w.agenda.get(day):
        for action in w.agenda.pop(day):
            _try(w, action)


def _try(w: World, action) -> None:
    """Run one scheduled step; a business rule saying no (no stock, credit limit) just skips it."""
    try:
        with w.db.begin_nested():
            action()
    except DomainError:
        pass


def _opening_stock(w: World, on: date) -> None:
    for warehouse in w.warehouses:
        if warehouse.code == "JKT-DC":
            lines = [inventory.CountLine(p.id, p.reorder_point + w.rng.randint(0, 4)) for p in w.products]
        else:
            lines = [inventory.CountLine(p.id, _store_target(p)) for p in w.products]
        adj = inventory.create_adjustment(w.db, w.users["warehouse"], warehouse.id, on, "Opening balance", lines)
        inventory.validate_adjustment(w.db, w.users["warehouse"], adj, kind="opening")
    w.db.commit()


def _store_target(p: Product) -> int:
    """What each store keeps on the shelf."""
    return max(1, p.reorder_point // 4) + 1


def _total(w: World, product_id: int) -> int:
    return inventory.total_on_hand(w.db, product_id)


def _on_hand(w: World, product_id: int, warehouse_id: int) -> int:
    level = w.db.scalar(select(StockLevel).filter_by(product_id=product_id, warehouse_id=warehouse_id))
    return level.on_hand if level else 0


def _daily_business(w: World, day: date) -> None:
    rng = w.rng
    # Sales: a few orders a day, busier towards month end and in recent months (growth).
    age = (today() - day).days
    for _ in range(rng.choices([1, 2, 3, 4, 5], weights=[15, 30, 30, 15, 5 + max(0, 25 - age // 15)])[0]):
        _new_sale(w, day)
    # Purchasing: replenish the distribution center twice a week.
    if day.weekday() in (0, 3):
        _replenish(w, day)
    # Stores pull stock from the distribution center on Wednesdays.
    if day.weekday() == 2:
        _restock_stores(w, day)


def _new_sale(w: World, day: date) -> None:
    rng = w.rng
    customer = rng.choice(w.customers)
    warehouse = rng.choice(w.warehouses)
    picks = rng.sample(w.products, rng.randint(1, 4))
    lines = []
    for p in picks:
        stock = _on_hand(w, p.id, warehouse.id)
        if stock:
            big = customer.group.code in ("RESELLER", "CORPORATE")
            lines.append(sales.SalesLineIn(p.id, min(stock, rng.randint(2, 4) if big else 1)))
    if not lines:
        return
    order = sales.save_order(w.db, w.users["sales"], sales.SalesOrderIn(customer.id, warehouse.id, day, lines))
    try:
        sales.confirm(w.db, w.users["sales"], order)
    except DomainError:
        return  # over the credit limit: stays a draft, like in real life
    ship_on = day + timedelta(days=rng.choice([1, 1, 1, 2, 3]))
    w.later(ship_on, lambda: _ship_and_invoice(w, order, ship_on))


def _ship_and_invoice(w: World, order: SalesOrder, on: date) -> None:
    qty = {li.id: min(li.qty - li.qty_delivered, _on_hand(w, li.product_id, order.warehouse_id)) for li in order.lines}
    if not any(qty.values()):
        return
    sales.deliver(w.db, w.users["warehouse"], order, qty, on)
    invoice = sales.create_invoice(w.db, w.users["accountant"], order, on)
    _schedule_payment(w, invoice, w.users["accountant"])
    if order.status == "partially_delivered":
        later = on + timedelta(days=w.rng.randint(5, 12))
        w.later(later, lambda: _ship_and_invoice(w, order, later))


def _schedule_payment(w: World, invoice: Invoice, user: User) -> None:
    rng = w.rng
    terms = (invoice.due_date - invoice.issue_date).days
    roll = rng.random()
    if roll < 0.86:  # on time
        days = [rng.randint(0, max(0, terms))]
    elif roll < 0.93:  # late
        days = [terms + rng.randint(3, 25)]
    elif roll < 0.98:  # in two parts
        days = [rng.randint(0, max(0, terms)), terms + rng.randint(1, 20)]
    elif (today() - invoice.issue_date).days < 100:  # not paid yet: shows up as overdue
        return
    else:  # an old one: paid, but very late
        days = [terms + rng.randint(30, 70)]
    for n, delta in enumerate(days):
        pay_on = invoice.issue_date + timedelta(days=delta)
        last = n == len(days) - 1

        def pay(pay_on=pay_on, last=last):
            amount = invoice.balance if last else invoice.balance // 2
            if amount:
                finance.register_payment(w.db, user, invoice, amount, pay_on,
                                         rng.choice(["bank_transfer", "bank_transfer", "card", "qris"]),
                                         f"TRX{rng.randint(10**7, 10**8)}")
        w.later(pay_on, pay)


def _replenish(w: World, day: date) -> None:
    rng = w.rng
    dc = w.warehouses[0]
    # A handful of products are on supplier backorder lately: they run low and show up on the dashboard.
    backorder = (today() - day).days < 120
    incoming = inventory.incoming_qty(w.db)
    low = [p for p in w.products
           if _total(w, p.id) + sum(q for (pid, _), q in incoming.items() if pid == p.id) <= p.reorder_point
           and not (backorder and p.id in w.backordered)]
    rng.shuffle(low)
    for chunk in (low[:8], low[8:16]):
        if not chunk:
            continue
        supplier = rng.choice(w.suppliers)
        lines = [purchasing.PurchaseLineIn(p.id, p.reorder_point * 2,
                                           int(p.avg_cost * rng.uniform(0.95, 1.05)) // 100 * 100) for p in chunk]
        order = purchasing.save_order(w.db, w.users["purchasing"], purchasing.PurchaseOrderIn(
            supplier.id, dc.id, day, lines, expected_date=day + timedelta(days=5)))
        purchasing.confirm(w.db, w.users["purchasing"], order)
        arrive = day + timedelta(days=rng.randint(3, 8))
        w.later(arrive, lambda order=order, arrive=arrive: _goods_arrive(w, order, arrive))


def _goods_arrive(w: World, order: PurchaseOrder, on: date) -> None:
    rng = w.rng
    # Now and then a supplier ships short and sends the rest a week later.
    short = rng.random() < 0.15 and order.status == "confirmed"
    qty = {li.id: (li.qty - li.qty_received) // (2 if short else 1) or (li.qty - li.qty_received) for li in order.lines}
    purchasing.receive(w.db, w.users["warehouse"], order, qty, on)
    bill = purchasing.create_bill(w.db, w.users["accountant"], order, on, f"INV/{order.supplier.code}/{rng.randint(1000, 9999)}")
    _schedule_payment(w, bill, w.users["accountant"])
    if order.status == "partially_received":
        later = on + timedelta(days=rng.randint(5, 9))
        w.later(later, lambda: _goods_arrive(w, order, later))


def _restock_stores(w: World, day: date) -> None:
    dc = w.warehouses[0]
    for store in w.warehouses[1:]:
        lines = []
        for p in w.products:
            need = _store_target(p) - _on_hand(w, p.id, store.id)
            available = _on_hand(w, p.id, dc.id)
            if need > 0 and available > 0:
                lines.append(inventory.QtyLine(p.id, min(need, available)))
        if lines:
            transfer = inventory.create_transfer(w.db, w.users["warehouse"], dc.id, store.id, day, lines[:15],
                                                 "Weekly store replenishment")
            _try(w, lambda transfer=transfer: inventory.validate_transfer(w.db, w.users["warehouse"], transfer))


def _work_in_progress(w: World) -> None:
    """A few open documents, so every status shows up on the screens."""
    rng, on = w.rng, today()
    for _ in range(3):  # drafts nobody confirmed yet
        customer = rng.choice(w.customers)
        sales.save_order(w.db, w.users["sales"], sales.SalesOrderIn(
            customer.id, w.warehouses[0].id, on, [sales.SalesLineIn(p.id, rng.randint(1, 3))
                                                  for p in rng.sample(w.products, 2)], note="Quote requested"))
    supplier = rng.choice(w.suppliers)
    purchasing.save_order(w.db, w.users["purchasing"], purchasing.PurchaseOrderIn(
        supplier.id, w.warehouses[0].id, on, [purchasing.PurchaseLineIn(p.id, 10, p.avg_cost)
                                              for p in rng.sample(w.products, 3)], note="Waiting for supplier quote"))
    count = inventory.create_adjustment(w.db, w.users["warehouse"], w.warehouses[1].id, on, "Spot check",
                                        [inventory.CountLine(p.id, max(0, _on_hand(w, p.id, w.warehouses[1].id) - 1))
                                         for p in rng.sample(w.products, 4)])
    assert count.status == "draft"
