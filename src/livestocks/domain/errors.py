"""Exceptions raised by domain rules.
DomainError is the base class for every rule violation.
InvalidTickerError also derives from ValueError for easy catching.
"""


class DomainError(Exception):
    """Base class for every domain-rule violation.
    Catch it to handle any invalid input in one place.
    Subclasses name the specific rule that was broken.
    """


class InvalidTickerError(DomainError, ValueError):
    """The text given is not a valid ticker.
    Raised by parse_ticker; the message lists the accepted formats.
    It is also a ValueError so generic handlers keep working.
    """
