"""Building blocks shared by every module: errors, numbering, money, audit trail, settings."""

from datetime import date, datetime

from sqlalchemy.orm import Session

from ..models import Activity, NumberSequence, Setting, User, utcnow


class DomainError(Exception):
    """A business rule said no. The API turns it into an HTTP error with this message."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def not_found(what: str) -> DomainError:
    return DomainError(404, f"{what} not found.")


def get_or_404(db: Session, model, id_: int, what: str):
    obj = db.get(model, id_)
    if obj is None:
        raise not_found(what)
    return obj


def next_number(db: Session, prefix: str, on: date) -> str:
    """Gapless per prefix and year: SO-2026-00001, SO-2026-00002, ...

    The row lock serialises concurrent requests on Postgres, so two documents never share
    a number (SQLite serialises writers anyway).
    """
    key = f"{prefix}-{on.year}"
    seq = db.get(NumberSequence, key, with_for_update=True)
    if seq is None:
        seq = NumberSequence(key=key, next_value=1)
        db.add(seq)
        db.flush()
    value = seq.next_value
    seq.next_value += 1
    return f"{prefix}-{on.year}-{value:05d}"


# ---------------------------------------------------------------- money (whole rupiah)


def _div_round(numerator: int, denominator: int) -> int:
    """Integer division rounding half up, for non-negative amounts."""
    return (numerator * 2 + denominator) // (denominator * 2)


def rupiah(amount: int) -> str:
    """Rp 1.234.567, the Indonesian way (dots group thousands)."""
    return f"Rp {amount:,}".replace(",", ".")


def line_amount(qty: int, unit_price: int, discount_pct: int = 0) -> int:
    return _div_round(qty * unit_price * (100 - discount_pct), 100)


def tax_amount(subtotal: int, rate_pct: int) -> int:
    return _div_round(subtotal * rate_pct, 100)


# ---------------------------------------------------------------- audit trail


def log(
    db: Session,
    user: User | None,
    entity_type: str,
    entity_id: int,
    action: str,
    message: str,
    at: datetime | None = None,
) -> None:
    db.add(Activity(user_id=user.id if user else None, entity_type=entity_type, entity_id=entity_id,
                    action=action, message=message[:500], at=at or utcnow()))


def stamp(on: date) -> datetime:
    """created_at for a document dated `on`: now for today's work, the business date for back-dated entries."""
    return utcnow() if on >= utcnow().date() else at_noon(on)


def at_noon(on: date) -> datetime:
    """Timestamp for a back-dated business event (seed data, documents dated in the past).
    Never in the future: an event dated today is stamped now at the latest."""
    return min(datetime(on.year, on.month, on.day, 5, 0), utcnow())


# ---------------------------------------------------------------- settings

DEFAULT_SETTINGS = {
    "company_name": "Kios Gawai Nusantara",
    "company_address": "Jl. Sudirman No. 1, Jakarta",
    "company_phone": "",
    "company_email": "",
    "company_tax_id": "",  # NPWP
    "bank_name": "",
    "bank_account": "",
    "bank_holder": "",
    "tax_rate": 11,
    "currency": "IDR",
}


def get_setting(db: Session, key: str):
    row = db.get(Setting, key)
    return row.value if row is not None else DEFAULT_SETTINGS.get(key)


def all_settings(db: Session) -> dict:
    stored = {s.key: s.value for s in db.query(Setting).all()}
    return {**DEFAULT_SETTINGS, **stored}


def set_setting(db: Session, key: str, value) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
