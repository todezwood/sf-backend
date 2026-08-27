from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import DatabaseError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _engine_kwargs(database_url: str) -> dict:
    if not database_url.startswith("sqlite"):
        return {}

    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if ":memory:" in database_url or "mode=memory" in database_url:
        # A plain in-memory SQLite database lives and dies with its connection.
        # StaticPool keeps a single connection alive so every request — and every
        # thread FastAPI hands work to — sees the same data for the process's lifetime.
        kwargs["poolclass"] = StaticPool
    return kwargs


settings = get_settings()

engine = create_engine(
    settings.database_url,
    echo=settings.sql_echo,
    **_engine_kwargs(settings.database_url),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db() -> None:
    """Create tables. Called on startup; safe to call repeatedly."""
    from app import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _apply_additive_upgrades()


def _apply_additive_upgrades() -> None:
    """
    Minimal in-place upgrade for pre-existing databases.

    `create_all` creates missing tables but never alters existing ones, so a
    persistent database (file-backed SQLite or Postgres) from before a column
    was added would fail every query. There is no migration tool in this
    project; for the columns we have added, a plain additive `ALTER TABLE` is
    safe, idempotent, and valid on every supported dialect.
    """
    inspector = inspect(engine)
    if not inspector.has_table("contacts"):
        return
    existing = {column["name"] for column in inspector.get_columns("contacts")}
    if "photo" not in existing:
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql("ALTER TABLE contacts ADD COLUMN photo TEXT")
        except DatabaseError:
            # Two workers can race this check-then-alter; the loser's ALTER
            # fails on the now-existing column. Confirm that is what happened
            # and re-raise anything else.
            refreshed = {column["name"] for column in inspect(engine).get_columns("contacts")}
            if "photo" not in refreshed:
                raise
    _migrate_flat_addresses(existing)


def _migrate_flat_addresses(contact_columns: set[str]) -> None:
    """
    Copy pre-existing flat address columns into the addresses table.

    Databases created before the one-to-many model kept the address on the
    contact row itself. When those legacy columns are present and the (new,
    empty) addresses table has no rows yet, carry the data over as one
    "Home" address per contact so the upgrade loses nothing. The legacy
    columns are left in place — SQLite cannot drop columns portably, and the
    ORM simply no longer reads them.
    """
    legacy = {"address", "city", "state", "postal_code", "country"}
    if not legacy <= contact_columns:
        return
    # The copy and the blanking of the source columns commit together: the
    # nulled columns are the migration marker, so a re-run — or a concurrent
    # worker, once the first commit lands — finds nothing left to move. The
    # NOT EXISTS guard additionally keeps the insert idempotent per contact.
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO addresses (contact_id, type, street, city, state, postal_code, country) "
            "SELECT id, 'Home', address, city, state, postal_code, country FROM contacts "
            "WHERE COALESCE(address, city, state, postal_code, country) IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM addresses WHERE addresses.contact_id = contacts.id)"
        )
        connection.exec_driver_sql(
            "UPDATE contacts SET address = NULL, city = NULL, state = NULL, "
            "postal_code = NULL, country = NULL "
            "WHERE COALESCE(address, city, state, postal_code, country) IS NOT NULL"
        )


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session that is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
