"""Alembic environment: runs migrations over a synchronous SQLite connection.
The database URL is supplied by livestocks.storage.db.upgrade_database through the config.
target_metadata lets `alembic revision --autogenerate` compare the models with the database.
"""

from alembic import context
from sqlalchemy import create_engine
from sqlmodel import SQLModel

import livestocks.storage.models  # noqa: F401  (registers the tables on SQLModel.metadata)

config = context.config
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Emit the migration SQL to the output instead of executing it."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run the migrations against the configured database."""
    engine = create_engine(config.get_main_option("sqlalchemy.url") or "")
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
