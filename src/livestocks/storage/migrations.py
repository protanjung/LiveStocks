"""Versioned schema migrations tracked with PRAGMA user_version.
MIGRATIONS lists the SQL steps in order and migrate() applies the pending ones.
Databases created before versioning are adopted by the idempotent first step.
"""

import sqlite3

from livestocks.storage.errors import MigrationError
from livestocks.storage.models import SCHEMA_V1

# MIGRATIONS[i] upgrades a database from version i to i + 1. The first step only uses
# CREATE ... IF NOT EXISTS, so it also adopts databases created before versioning existed.
MIGRATIONS: list[str] = [SCHEMA_V1]


def migrate(db: sqlite3.Connection) -> int:
    """Apply every pending migration in order and return the resulting version.
    Raises MigrationError if the database is newer than this code understands.
    The first step is idempotent, so it also adopts pre-versioning databases.
    """
    current = int(db.execute("PRAGMA user_version").fetchone()[0])
    if current > len(MIGRATIONS):
        raise MigrationError(
            f"database schema v{current} is newer than supported v{len(MIGRATIONS)}"
        )
    for version in range(current, len(MIGRATIONS)):
        db.executescript(MIGRATIONS[version])
        db.execute(f"PRAGMA user_version = {version + 1}")
    db.commit()
    return len(MIGRATIONS)
