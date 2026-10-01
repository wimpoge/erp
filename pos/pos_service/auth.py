"""Staff login: scrypt password hashes, server-side sessions in an httpOnly cookie."""

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import StaffSession, User, utcnow

COOKIE_NAME = "pos_session"
MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=5)

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
    return hmac.compare_digest(candidate.hex(), digest)


# Compared against when the username does not exist, so a wrong username takes as long as a wrong password.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class LoginError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def authenticate(db: Session, username: str, password: str) -> User:
    user = db.query(User).filter(User.username == username.strip().lower()).one_or_none()
    if user is None or not user.active:
        verify_password(password, _DUMMY_HASH)
        raise LoginError(401, "Wrong username or password.")
    now = utcnow()
    if user.locked_until and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise LoginError(423, f"Too many wrong attempts. Try again in {minutes} minute(s) or ask an admin.")
    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.locked_until = now + LOCKOUT
            user.failed_logins = 0
        db.commit()
        raise LoginError(401, "Wrong username or password.")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    return user


def start_session(db: Session, user: User, hours: int) -> tuple[str, int]:
    token = secrets.token_urlsafe(32)
    db.add(StaffSession(token_hash=_token_hash(token), user_id=user.id, expires_at=utcnow() + timedelta(hours=hours)))
    db.commit()
    return token, hours * 3600


def end_session(db: Session, token: str | None) -> None:
    if token:
        db.query(StaffSession).filter(StaffSession.token_hash == _token_hash(token)).delete()
        db.commit()


def _request_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.startswith("Bearer "):
        return header.removeprefix("Bearer ")
    return request.cookies.get(COOKIE_NAME)


def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    token = _request_token(request)
    session = db.get(StaffSession, _token_hash(token)) if token else None
    if session is None or session.expires_at < utcnow() or not session.user.active:
        raise HTTPException(401, "Please log in.")
    return session.user


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Only an admin can do this.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
Admin = Annotated[User, Depends(require_admin)]


def check_location(user: User, location_id: int) -> None:
    """Cashiers work in their own store only."""
    if user.role != "admin" and user.location_id != location_id:
        raise HTTPException(403, "You can only work in your own store.")
