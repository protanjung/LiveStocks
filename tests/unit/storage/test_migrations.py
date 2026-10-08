import sqlite3

import pytest
from alembic import command

from livestocks.storage import MigrationError, Store
from livestocks.storage.db import alembic_config, upgrade_database

BASELINE = "0001"

# The schema the app created before Alembic, tracked with PRAGMA user_version = 2.
PRE_ALEMBIC_SCHEMA = """
CREATE TABLE tickers (
    exchange TEXT NOT NULL, symbol TEXT NOT NULL, name TEXT, added_at INTEGER NOT NULL,
    last_fetch INTEGER, next_fetch INTEGER NOT NULL DEFAULT 0, last_error TEXT,
    fail_count INTEGER NOT NULL DEFAULT 0, dead INTEGER NOT NULL DEFAULT 0, {extra}
    PRIMARY KEY (exchange, symbol)
);
CREATE TABLE forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, exchange TEXT NOT NULL, symbol TEXT NOT NULL,
    fetched_at INTEGER NOT NULL, name TEXT, price REAL, change_pct REAL, pt_avg REAL, pt_high REAL,
    pt_low REAL, n_analysts INTEGER, rating_mark REAL, n_ratings INTEGER, ath REAL,
    next_earnings INTEGER
);
CREATE TABLE prices (
    exchange TEXT NOT NULL, symbol TEXT NOT NULL, ts INTEGER NOT NULL, close REAL NOT NULL,
    PRIMARY KEY (exchange, symbol, ts)
);
CREATE TABLE extras (
    exchange TEXT NOT NULL, symbol TEXT NOT NULL, fetched_at INTEGER NOT NULL, data TEXT NOT NULL,
    PRIMARY KEY (exchange, symbol)
);
"""


def tables(path) -> set[str]:
    db = sqlite3.connect(path)
    try:
        return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        db.close()


def revision(path) -> str:
    db = sqlite3.connect(path)
    try:
        return db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        db.close()


class TestUpgradeDatabase:
    def test_new_database_gets_every_table_and_the_baseline_revision(self, tmp_path):
        path = tmp_path / "new.db"

        upgrade_database(path)

        assert {"tickers", "forecasts", "prices", "extras", "alembic_version"} <= tables(path)
        assert revision(path) == BASELINE

    def test_running_twice_changes_nothing(self, tmp_path):
        path = tmp_path / "twice.db"
        upgrade_database(path)

        upgrade_database(path)

        assert revision(path) == BASELINE

    def test_database_from_the_pre_alembic_scheme_is_adopted_with_its_rows(self, tmp_path):
        path = tmp_path / "legacy.db"
        legacy = sqlite3.connect(path)
        legacy.executescript(PRE_ALEMBIC_SCHEMA.format(extra="error_kind TEXT,"))
        legacy.execute("PRAGMA user_version = 2")
        legacy.execute(
            "INSERT INTO tickers (exchange, symbol, added_at, last_error, error_kind) "
            "VALUES ('IDX', 'TLKM', 5, 'boom', 'upstream')"
        )
        legacy.commit()
        legacy.close()

        upgrade_database(path)

        db = sqlite3.connect(path)
        assert db.execute("SELECT symbol, last_error, error_kind FROM tickers").fetchall() == [
            ("TLKM", "boom", "upstream")
        ]
        db.close()
        assert revision(path) == BASELINE

    def test_database_older_than_the_last_pre_alembic_version_is_rejected(self, tmp_path):
        path = tmp_path / "v1.db"
        old = sqlite3.connect(path)
        old.executescript(PRE_ALEMBIC_SCHEMA.format(extra=""))
        old.commit()
        old.close()

        with pytest.raises(MigrationError, match="predates"):
            upgrade_database(path)


class TestStoreInitialize:
    async def test_file_store_is_migrated_and_usable(self, tmp_path):
        store = Store(tmp_path / "data" / "app.db")

        await store.initialize()

        assert await store.add_ticker("IDX", "TLKM") is True
        assert [r.key for r in await store.rows()] == ["IDX:TLKM"]
        await store.close()
        assert revision(tmp_path / "data" / "app.db") == BASELINE

    async def test_data_survives_reopening_the_database(self, tmp_path):
        path = tmp_path / "app.db"
        first = Store(path)
        await first.initialize()
        await first.add_ticker("IDX", "TLKM")
        await first.close()

        second = Store(path)
        await second.initialize()

        assert [r.key for r in await second.rows()] == ["IDX:TLKM"]
        await second.close()


class TestModelsMatchMigrations:
    def test_models_and_migrations_describe_the_same_schema(self, tmp_path):
        path = tmp_path / "check.db"
        upgrade_database(path)

        command.check(alembic_config(path))  # raises if autogenerate would find a difference
