"""python -m pos_service.cli <command>

  init-db [--reset]        create tables
  sync                     pull master data from the ERP
  push-pending             retry queued ERP pushes (run it from a scheduler)
  create-user USERNAME --name NAME --password PW [--admin] [--store CODE]
  demo-users               admin/admin123 plus one cashier per store (kasir1/kasir123, ...)
"""

import argparse
import json
import sys

import httpx
from sqlalchemy import select

from .auth import hash_password
from .config import get_settings
from .db import make_session_factory
from .erp_client import ErpClient
from .models import Base, Location, User
from .orders import push_due
from .sync import run_sync


def main() -> None:
    parser = argparse.ArgumentParser(prog="pos_service.cli")
    parser.add_argument("command", choices=["init-db", "sync", "push-pending", "create-user", "demo-users"])
    parser.add_argument("username", nargs="?")
    parser.add_argument("--reset", action="store_true", help="init-db: drop all tables first")
    parser.add_argument("--name", help="create-user: full name")
    parser.add_argument("--password", help="create-user: at least 6 characters")
    parser.add_argument("--admin", action="store_true", help="create-user: admin instead of cashier")
    parser.add_argument("--store", help="create-user: store code, e.g. KG01 (required for cashiers)")
    args = parser.parse_args()

    settings = get_settings()
    session_factory = make_session_factory(settings.database_url)
    engine = session_factory.kw["bind"]
    if args.command == "init-db":
        if args.reset:
            Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        print("POS tables ready")
        return

    if args.command in ("create-user", "demo-users"):
        with session_factory() as db:
            if args.command == "create-user":
                create_user(db, args)
            else:
                demo_users(db)
        return

    erp = ErpClient(
        httpx.Client(base_url=settings.erp_base_url, timeout=30),
        settings.erp_client_id, settings.erp_client_secret, settings.erp_app_code,
    )
    with session_factory() as db:
        if args.command == "sync":
            run = run_sync(db, erp)
            print(json.dumps({"run": run.id, "status": run.status, "summary": run.summary}, indent=2))
        else:
            print(json.dumps(push_due(db, erp, settings.push_max_attempts)))


def _add_user(db, username: str, name: str, password: str, role: str, location: Location | None) -> None:
    if db.scalar(select(User).filter_by(username=username)) is not None:
        print(f"  {username}: exists, skipped")
        return
    db.add(User(username=username, full_name=name, password_hash=hash_password(password), role=role,
                location_id=location.id if location else None))
    db.commit()
    where = location.name if location else "all stores"
    print(f"  {username} / {password}  ({role}, {where})")


def create_user(db, args) -> None:
    if not (args.username and args.name and args.password) or len(args.password) < 6:
        sys.exit("create-user needs USERNAME --name NAME --password PW (6+ characters)")
    location = None
    if args.store:
        location = db.scalar(select(Location).filter_by(code=args.store.upper()))
        if location is None:
            sys.exit(f"unknown store {args.store}; run a sync first")
    elif not args.admin:
        sys.exit("a cashier needs --store CODE")
    _add_user(db, args.username.lower(), args.name, args.password, "admin" if args.admin else "cashier", location)


def demo_users(db) -> None:
    locations = db.scalars(select(Location).filter_by(active=True).order_by(Location.code)).all()
    if not locations:
        sys.exit("no stores yet: run `sync` first")
    print("Demo accounts:")
    _add_user(db, "admin", "Admin Kantor Pusat", "admin123", "admin", None)
    for n, location in enumerate(locations, start=1):
        _add_user(db, f"kasir{n}", f"Kasir {location.city}", "kasir123", "cashier", location)


if __name__ == "__main__":
    main()
