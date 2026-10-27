"""Pure domain layer: value objects, ticker parsing and rating rules.
Nothing here performs I/O, so every other layer can import it freely.
Public names are re-exported from this package root.
"""

from livestocks.domain.errors import DomainError, InvalidTickerError
from livestocks.domain.models import (
    CalendarEntry,
    CalendarKind,
    Dividend,
    DividendPayment,
    ErrorKind,
    Extras,
    Forecast,
    Period,
    PriceBar,
    RatingTone,
    SuggestionReport,
    TickerId,
    TickerStatus,
    TrackedTicker,
)
from livestocks.domain.ratings import rating_label
from livestocks.domain.tickers import parse_ticker

__all__ = [
    "CalendarEntry",
    "CalendarKind",
    "Dividend",
    "DividendPayment",
    "DomainError",
    "ErrorKind",
    "Extras",
    "Forecast",
    "InvalidTickerError",
    "Period",
    "PriceBar",
    "RatingTone",
    "SuggestionReport",
    "TickerId",
    "TickerStatus",
    "TrackedTicker",
    "parse_ticker",
    "rating_label",
]
