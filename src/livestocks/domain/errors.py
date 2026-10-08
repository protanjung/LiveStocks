"""Exceptions raised by domain rules."""


class DomainError(Exception):
    """Base class for every domain-rule violation."""


class InvalidTickerError(DomainError, ValueError):
    """The text given is not a valid ticker."""
