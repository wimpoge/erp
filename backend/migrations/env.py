from alembic import context

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
    # Same URL handling as the app (ERP_DATABASE_URL, postgres:// rewriting).
    engine = make_engine(get_settings().database_url)
    with engine.connect() as connection:
        # Batch mode lets ALTERs work on SQLite too.
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
