import sqlite3

import pytest

from livestocks.storage import MigrationError, Store
from livestocks.storage.migrations import MIGRATIONS, migrate
from livestocks.storage.models import SCHEMA_V1


def user_version(db: sqlite3.Connection) -> int:
    return db.execute("PRAGMA user_version").fetchone()[0]


class TestMigrate:
    def test_new_database_is_brought_to_the_latest_version(self):
        db = sqlite3.connect(":memory:")

        assert migrate(db) == len(MIGRATIONS)
        assert user_version(db) == len(MIGRATIONS)

    def test_database_created_before_versioning_keeps_its_rows(self, tmp_path):
        path = tmp_path / "legacy.db"
        legacy = sqlite3.connect(path)
        legacy.executescript(
            SCHEMA_V1
        )  # what the app created before migrations existed (user_version 0)
        legacy.execute("INSERT INTO tickers (exchange, symbol, added_at) VALUES ('IDX', 'TLKM', 5)")
        legacy.commit()
        legacy.close()

        store = Store(path)

        assert [r.key for r in store.rows()] == ["IDX:TLKM"]
        assert user_version(store._db) == len(MIGRATIONS)
        store.close()

    def test_running_twice_is_a_no_op(self):
        db = sqlite3.connect(":memory:")
        migrate(db)

        assert migrate(db) == len(MIGRATIONS)

    def test_database_from_a_newer_version_is_rejected(self):
        db = sqlite3.connect(":memory:")
        db.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")

        with pytest.raises(MigrationError, match="newer"):
            migrate(db)
