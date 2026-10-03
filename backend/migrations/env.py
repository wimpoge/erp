from alembic import context
from sqlalchemy import create_engine

from erp.config import get_settings
from erp.db import make_engine
from erp.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_settings().database_url
    # Same URL handling as the app (ERP_DATABASE_URL, postgres:// rewriting). On SQLite, a plain
    # connection: batch migrations rebuild tables, which the app's foreign-key enforcement blocks.
    engine = create_engine(url) if url.startswith("sqlite") else make_engine(url)
    with engine.connect() as connection:
        # Batch mode lets ALTERs work on SQLite too.
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
