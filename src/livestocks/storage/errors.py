"""Exceptions raised by the persistence layer.
StorageError is the base class for every database failure.
MigrationError means the schema cannot be brought to the expected version.
"""


class StorageError(Exception):
    """Base class for every persistence failure.
    Catch it to handle any database problem in one place.
    Subclasses carry the specific cause.
    """


class MigrationError(StorageError):
    """The database schema cannot be brought to the version this code expects.
    Typically the file was written by a newer release of LiveStocks.
    Opening the store fails rather than risking data corruption.
    """
