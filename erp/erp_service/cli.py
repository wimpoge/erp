"""python -m erp_service.cli {init-db,seed} [--reset]"""

import argparse

from sqlalchemy import select

from .config import get_settings
from .db import make_session_factory
from .models import Base, Store
from .seed import seed


def main() -> None:
    parser = argparse.ArgumentParser(prog="erp_service.cli")
    parser.add_argument("command", choices=["init-db", "seed"])
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    args = parser.parse_args()

    settings = get_settings()
    session_factory = make_session_factory(settings.database_url)
    engine = session_factory.kw["bind"]
    if args.reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    if args.command == "init-db":
        print("ERP tables ready")
        return

    with session_factory() as db:
        if db.scalar(select(Store).limit(1)) is not None:
            print("ERP already has data; use --reset to start over")
            return
        seed(db, client_id=settings.client_id, client_secret=settings.client_secret, app_code=settings.app_code)
    print(f"ERP seeded; API client '{settings.client_id}' / app code '{settings.app_code}'")


if __name__ == "__main__":
    main()
