"""Fake but realistic master data for a small chain of phone & accessories stores."""

import random

from faker import Faker
from sqlalchemy.orm import Session

from .main import hash_secret
from .models import ApiClient, Customer, CustomerGroup, Product, Register, Stock, Store

CITIES = ["Jakarta Selatan", "Bandung", "Surabaya", "Padang", "Medan", "Yogyakarta"]

# category -> (brands, min price, max price) in rupiah
CATEGORIES = {
    "Smartphone": (["Samsung", "Xiaomi", "Oppo", "Vivo", "Realme", "Infinix"], 1_500_000, 12_000_000),
    "Phone case": (["Spigen", "Nillkin", "Casepro"], 25_000, 250_000),
    "Charger": (["Anker", "Baseus", "Ugreen"], 60_000, 450_000),
    "Cable": (["Anker", "Baseus", "Ugreen"], 25_000, 150_000),
    "Earbuds": (["JBL", "Soundcore", "QCY"], 150_000, 1_800_000),
    "Screen protector": (["Nillkin", "Casepro"], 20_000, 120_000),
    "Power bank": (["Anker", "Xiaomi", "Baseus"], 150_000, 700_000),
}
VARIANTS = ["Lite", "Pro", "Max", "Plus", "Slim", "Mini", "Neo", "Air"]

GROUPS = [("RETAIL", "Retail", 0), ("MEMBER", "Member", 5), ("RESELLER", "Reseller", 10)]


def _product_name(rng: random.Random, category: str, brand: str) -> str:
    variant = rng.choice(VARIANTS)
    if category == "Smartphone":
        return f"{brand} {rng.choice('ACGKMNRX')}{rng.randint(10, 99)} {variant} {rng.choice([64, 128, 256])}GB"
    if category == "Charger":
        return f"{brand} Charger {variant} {rng.choice([20, 33, 45, 65])}W"
    if category == "Power bank":
        return f"{brand} Power Bank {variant} {rng.choice([10_000, 20_000])}mAh"
    if category == "Cable":
        return f"{brand} USB-C Cable {variant} {rng.choice([1, 1.5, 2])}m"
    return f"{brand} {category.title()} {variant} {rng.randint(1, 99):02d}"


def seed(
    db: Session,
    *,
    stores: int = 3,
    products: int = 80,
    customers: int = 60,
    seed_value: int = 42,
    client_id: str = "pos-dev",
    client_secret: str = "pos-dev-secret",
    app_code: str = "POS",
) -> None:
    rng = random.Random(seed_value)
    fake = Faker("id_ID")
    fake.seed_instance(seed_value)

    db.add(ApiClient(client_id=client_id, secret_hash=hash_secret(client_secret), app_code=app_code))

    groups = [CustomerGroup(code=code, name=name, discount_rate=rate) for code, name, rate in GROUPS]
    db.add_all(groups)

    store_rows = []
    for i, city in enumerate(CITIES[:stores], start=1):
        store = Store(code=f"KG{i:02d}", name=f"Kios Gawai {city}", city=city)
        store.registers = [Register(code=f"KG{i:02d}-R{n}", name=f"Kasir {n}") for n in (1, 2)]
        store_rows.append(store)
    db.add_all(store_rows)

    product_rows = []
    for n in range(1, products + 1):
        category = rng.choice(list(CATEGORIES))
        brands, low, high = CATEGORIES[category]
        brand = rng.choice(brands)
        product_rows.append(
            Product(
                sku=f"{category[:3].upper()}-{n:04d}",
                name=_product_name(rng, category, brand),
                barcode=fake.unique.ean13(),
                brand=brand,
                category=category,
                price=round(rng.randint(low, high), -3),
            )
        )
    db.add_all(product_rows)

    db.flush()  # assigns store ids
    for store in store_rows:
        for product in product_rows:
            db.add(Stock(product=product, store_id=store.id, on_hand=rng.choice([0, 1, 2, 3, 5, 8, 12, 20, 30])))

    for n in range(1, customers + 1):
        db.add(
            Customer(
                code=f"C{n:05d}",
                name=fake.name(),
                phone=fake.phone_number(),
                email=fake.email() if rng.random() < 0.7 else None,
                group=rng.choices(groups, weights=[70, 22, 8])[0],
            )
        )
    db.commit()
