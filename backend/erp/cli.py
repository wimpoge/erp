"""python -m erp.cli <command>

  migrate                   create/upgrade the database schema (Alembic)
  seed [--reset]            demo company with a year of history (refuses if data exists)
  create-admin EMAIL NAME   an administrator account; asks for the password
"""

import argparse
import getpass
import sys
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from .config import get_settings
from .db import make_session_factory
from .models import Base, User
from .services.auth import hash_password

ROOT = Path(__file__).resolve().parent.parent


def migrate() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(config, "head")


def main() -> None:
    parser = argparse.ArgumentParser(prog="erp.cli")
    parser.add_argument("command", choices=["migrate", "seed", "create-admin"])
    parser.add_argument("args", nargs="*")
    parser.add_argument("--reset", action="store_true", help="seed: drop every table first (destroys data)")
    args = parser.parse_args()
    settings = get_settings()

    if args.command == "migrate":
        migrate()
        print("Schema is up to date.")
        return

    factory = make_session_factory(settings.database_url)
    if args.command == "seed":
        if args.reset:
            Base.metadata.drop_all(factory.kw["bind"])
            with factory.kw["bind"].begin() as conn:
                conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
        migrate()
        with factory() as db:
            if db.scalar(select(User).limit(1)) is not None:
                sys.exit("The database already has data. Use --reset to wipe it and seed again.")
            from .seed import seed  # Faker is a dev dependency; only needed here

            started = time.monotonic()
            result = seed(db)
        print(f"Seeded in {time.monotonic() - started:.0f}s. Log in with any of:")
        for email in result["users"]:
            print(f"  {email} / {result['password']}")
        return

    if len(args.args) != 2:
        sys.exit('usage: create-admin EMAIL "FULL NAME"')
    email, name = args.args
    password = getpass.getpass("Password (8+ characters): ")
    if len(password) < 8:
        sys.exit("Password too short.")
    with factory() as db:
        db.add(User(email=email.lower(), full_name=name, role="admin", password_hash=hash_password(password)))
        db.commit()
    print(f"Administrator {email} created.")


if __name__ == "__main__":
    main()
