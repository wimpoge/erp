"""Users, roles, API clients and company settings (administrators)."""

import secrets
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from ..models import ApiClient, User, utcnow
from ..permissions import PERMISSIONS, ROLES
from ..services.auth import hash_password, sha256
from ..services.common import DomainError, all_settings, get_or_404, set_setting
from .deps import Db, can

router = APIRouter(prefix="/api/settings", tags=["settings"])

RoleName = Literal["admin", "manager", "sales", "purchasing", "warehouse", "accountant", "cashier"]


@router.get("/roles")
def list_roles(_: can("settings.manage")) -> list[dict]:
    return [{"name": name, "label": r["label"],
             "permissions": [{"key": p, "label": PERMISSIONS[p]} for p in sorted(r["permissions"])]}
            for name, r in ROLES.items()]


def user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "email": u.email, "full_name": u.full_name, "role": u.role,
            "role_label": ROLES.get(u.role, {}).get("label", u.role), "active": u.active,
            "locked": bool(u.locked_until and u.locked_until > utcnow()), "last_login_at": u.last_login_at}


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9._-]+$")
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    role: RoleName
    password: str = Field(min_length=8, max_length=200)


class UserPatch(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=120)
    role: RoleName | None = None
    active: bool | None = None
    password: str | None = Field(None, min_length=8, max_length=200)
    unlock: bool | None = None


@router.get("/users")
def list_users(db: Db, _: can("settings.manage")) -> list[dict]:
    return [user_out(u) for u in db.scalars(select(User).order_by(User.full_name))]


@router.post("/users", status_code=201)
def create_user(body: UserIn, db: Db, _: can("settings.manage")) -> dict:
    email, username = body.email.lower(), body.username.lower()
    if db.scalar(select(User).where((User.email == email) | (User.username == username))):
        raise DomainError(409, "That username or email is already used.")
    user = User(username=username, email=email, full_name=body.full_name.strip(), role=body.role,
                password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return user_out(user)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, db: Db, admin: can("settings.manage")) -> dict:
    user = get_or_404(db, User, user_id, "User")
    changes = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (changes.get("active") is False or changes.get("role", "admin") != "admin"):
        raise DomainError(422, "You cannot deactivate yourself or remove your own admin role.")
    for field in ("full_name", "role", "active"):
        if changes.get(field) is not None:
            setattr(user, field, changes[field])
    if body.password:
        user.password_hash = hash_password(body.password)
    if body.unlock or body.password:
        user.locked_until, user.failed_logins = None, 0
    db.commit()
    return user_out(user)


# ---------------------------------------------------------------- company


class CompanyIn(BaseModel):
    company_name: str = Field(min_length=1, max_length=120)
    company_address: str = Field("", max_length=250)
    company_phone: str = Field("", max_length=40)
    company_email: str = Field("", max_length=120)
    company_tax_id: str = Field("", max_length=40)
    bank_name: str = Field("", max_length=80)
    bank_account: str = Field("", max_length=40)
    bank_holder: str = Field("", max_length=120)
    tax_rate: int = Field(ge=0, le=50)
    # POS loyalty: rupiah spent per point earned (0: no points), and a point's value when spent.
    loyalty_earn_per: int = Field(10_000, ge=0)
    loyalty_point_value: int = Field(100, ge=1)


@router.get("/company")
def get_company(db: Db, _: can("catalog.read")) -> dict:
    return all_settings(db)


@router.put("/company")
def update_company(body: CompanyIn, db: Db, _: can("settings.manage")) -> dict:
    for key, value in body.model_dump().items():
        set_setting(db, key, value)
    db.commit()
    return all_settings(db)


# ---------------------------------------------------------------- integration API clients


def client_out(c: ApiClient) -> dict:
    return {"id": c.id, "name": c.name, "client_id": c.client_id, "active": c.active, "created_at": c.created_at,
            "last_used_at": c.last_used_at}


class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.get("/api-clients")
def list_clients(db: Db, _: can("settings.manage")) -> list[dict]:
    return [client_out(c) for c in db.scalars(select(ApiClient).order_by(ApiClient.id))]


@router.post("/api-clients", status_code=201)
def create_client(body: ClientIn, db: Db, _: can("settings.manage")) -> dict:
    secret = secrets.token_urlsafe(32)
    client = ApiClient(name=body.name.strip(), client_id=f"cli_{secrets.token_hex(8)}", secret_hash=sha256(secret))
    db.add(client)
    db.commit()
    # The secret is only ever returned here; we keep its hash.
    return {**client_out(client), "client_secret": secret}


class ClientPatch(BaseModel):
    active: bool


@router.patch("/api-clients/{client_id}")
def toggle_client(client_id: int, body: ClientPatch, db: Db, _: can("settings.manage")) -> dict:
    client = get_or_404(db, ApiClient, client_id, "API client")
    client.active = body.active
    db.commit()
    return client_out(client)
