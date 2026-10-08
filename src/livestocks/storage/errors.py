"""Exceptions raised by the persistence layer."""


class StorageError(Exception):
    """Base class for every persistence failure."""


class MigrationError(StorageError):
    """The database schema cannot be brought to the version this code expects."""
