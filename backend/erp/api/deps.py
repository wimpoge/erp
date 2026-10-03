"""Shared request plumbing: who is calling, may they, and list pagination/sorting."""

from typing import Annotated, Any, Callable

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..permissions import permissions_for
from ..services.auth import user_for_token

SESSION_COOKIE = "erp_session"

Db = Annotated[Session, Depends(get_db)]


def current_user(request: Request, db: Db) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user = user_for_token(db, token) if token else None
    if user is None:
        raise HTTPException(401, "Please log in.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require(permission: str) -> Callable[[User], User]:
    def check(user: CurrentUser) -> User:
        if permission not in permissions_for(user.role):
            raise HTTPException(403, "Your role does not allow this.")
        return user

    return check


def can(permission: str):
    """Dependency that returns the user if they hold `permission`."""
    return Annotated[User, Depends(require(permission))]


class ListParams:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=200)] = 25,
        q: Annotated[str | None, Query(max_length=100)] = None,
        sort: Annotated[str | None, Query(max_length=40)] = None,
    ):
        self.page = page
        self.page_size = page_size
        self.q = q.strip() if q and q.strip() else None
        self.sort = sort


Params = Annotated[ListParams, Depends()]


def paginate(
    db: Session,
    stmt: Select,
    params: ListParams,
    serialize: Callable[[Any], dict],
    sortable: dict[str, Any] | None = None,
    default_sort: list | None = None,
    scalars: bool = True,
) -> dict:
    """Apply `?sort=field` / `?sort=-field` (whitelisted) and page the result."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    order = list(default_sort or [])
    if params.sort and sortable:
        key = params.sort.lstrip("-")
        if key in sortable:
            column = sortable[key]
            order = [column.desc() if params.sort.startswith("-") else column.asc(), *order]
    if order:
        stmt = stmt.order_by(*order)
    stmt = stmt.offset((params.page - 1) * params.page_size).limit(params.page_size)
    rows = db.scalars(stmt).all() if scalars else db.execute(stmt).all()
    return {"items": [serialize(r) for r in rows], "total": total, "page": params.page, "page_size": params.page_size}


def like(value: str) -> str:
    return f"%{value.replace('%', '').replace('_', ' ')}%"
