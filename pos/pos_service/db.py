from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker


def make_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)

    engine = create_engine(url, connect_args={"check_same_thread": False})

    # pysqlite manages transactions itself and breaks SAVEPOINTs; hand control back to
    # SQLAlchemy (documented recipe). Also: foreign keys on (SQLite skips them by default)
    # and WAL, so an open reader does not block a background writer.
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        dbapi_conn.isolation_level = None
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        dbapi_conn.execute("PRAGMA journal_mode=WAL")

    @event.listens_for(engine, "begin")
    def _on_begin(conn):
        conn.exec_driver_sql("BEGIN")

    return engine


def make_session_factory(url: str) -> sessionmaker:
    return sessionmaker(make_engine(url), expire_on_commit=False)
