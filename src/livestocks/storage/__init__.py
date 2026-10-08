"""SQLite persistence: tracked tickers, forecast snapshots, prices and extras.
Store is the only class other layers need; errors live in storage.errors.
Schema upgrades run automatically when a Store is opened.
"""

from livestocks.storage.errors import MigrationError, StorageError
from livestocks.storage.store import Store

__all__ = ["MigrationError", "StorageError", "Store"]
