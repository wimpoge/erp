"""python -m pos_service.cli {init-db,sync,push-pending} [--reset]

`push-pending` is meant for a scheduler (cron / a loop in docker compose).
"""

import argparse
import json

import httpx

from .config import get_settings
from .db import make_session_factory
from .erp_client import ErpClient
from .models import Base
from .orders import push_due
from .sync import run_sync


def main() -> None:
    parser = argparse.ArgumentParser(prog="pos_service.cli")
    parser.add_argument("command", choices=["init-db", "sync", "push-pending"])
    parser.add_argument("--reset", action="store_true", help="init-db: drop all tables first")
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


if __name__ == "__main__":
    main()
