"""Passwords (scrypt), server-side sessions, lockout after repeated failures."""

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuthSession, User, utcnow
from .common import DomainError

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


# Checked when the username is unknown, so a wrong username takes as long as a wrong password.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def authenticate(db: Session, login: str, password: str) -> User:
    """Log in with a username (or, as a fallback, the email address)."""
    login = login.strip().lower()
    user = db.scalar(select(User).where((User.username == login) | (User.email == login)))
    if user is None or not user.active:
        verify_password(password, _DUMMY_HASH)
        raise DomainError(401, "Wrong username or password.")
    now = utcnow()
    if user.locked_until and user.locked_until > now:
        minutes = int((user.locked_until - now).total_seconds() // 60) + 1
        raise DomainError(423, f"Too many failed attempts. Try again in {minutes} minute(s) or ask an administrator.")
    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.locked_until = now + LOCKOUT
            user.failed_logins = 0
        db.commit()
        raise DomainError(401, "Wrong username or password.")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    return user


def start_session(db: Session, user: User, hours: int) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=sha256(token), user_id=user.id, expires_at=utcnow() + timedelta(hours=hours)))
    return token


def user_for_token(db: Session, token: str) -> User | None:
    session = db.get(AuthSession, sha256(token))
    if session is None or session.expires_at < utcnow() or not session.user.active:
        return None
    return session.user


def end_session(db: Session, token: str) -> None:
    db.query(AuthSession).filter(AuthSession.token_hash == sha256(token)).delete()
