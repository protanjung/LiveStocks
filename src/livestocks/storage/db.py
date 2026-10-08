"""Database engine creation and schema upgrades.
create_engine builds the async SQLite engine with sensible pragmas.
upgrade_database runs the Alembic migrations on a plain synchronous connection.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from livestocks.storage.errors import MigrationError

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _file_path(path: Path | str) -> Path:
    resolved = Path(path).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def create_engine(path: Path | str) -> AsyncEngine:
    """Create the async SQLite engine for a database file, creating its folder if needed.
    Connections use write-ahead logging and wait up to 30 seconds for a lock.
    Each operation takes its own pooled connection, so concurrent crawls do not interleave.
    """
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{_file_path(path).as_posix()}", connect_args={"timeout": 30}
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # pyright: ignore[reportUnusedFunction]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def _alembic_config(path: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    return config


def upgrade_database(path: Path | str) -> None:
    """Bring a database file to the latest schema, adopting one that predates Alembic.
    A database from the old PRAGMA user_version scheme is stamped at the baseline first.
    Raises MigrationError if such a database is older than that scheme's last version.
    """
    target = _file_path(path)
    config = _alembic_config(target)
    engine = create_sync_engine(f"sqlite:///{target.as_posix()}")
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            if "tickers" in tables and "alembic_version" not in tables:
                columns = {c["name"] for c in inspector.get_columns("tickers")}
                if "error_kind" not in columns:
                    raise MigrationError(
                        f"{target} predates schema version 2; delete it or upgrade it "
                        "with an older release first"
                    )
                command.stamp(config, "head")
    finally:
        engine.dispose()
    command.upgrade(config, "head")
