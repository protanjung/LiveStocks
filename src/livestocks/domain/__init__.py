"""Pure domain layer: value objects, ticker parsing and rating rules.
Nothing here performs I/O, so every other layer can import it freely.
Public names are re-exported from this package root.
"""

from livestocks.domain.errors import DomainError, InvalidTickerError
from livestocks.domain.hunt import (
    Check,
    CheckStatus,
    HuntStyle,
    hunt_checks,
    hunt_factors,
    hunt_score,
)
from livestocks.domain.models import (
    CalendarEntry,
    CalendarKind,
    Dividend,
    DividendPayment,
    ErrorKind,
    ExDateEvent,
    Extras,
    Forecast,
    Period,
    PriceBar,
    RatingTone,
    SuggestionReport,
    TickerId,
    TickerStatus,
    TrackedTicker,
    TrapStats,
)
from livestocks.domain.ratings import rating_label
from livestocks.domain.tickers import parse_ticker
from livestocks.domain.trading_days import shift_trading_days

__all__ = [
    "CalendarEntry",
    "CalendarKind",
    "Check",
    "CheckStatus",
    "Dividend",
    "DividendPayment",
    "DomainError",
    "ErrorKind",
    "ExDateEvent",
    "Extras",
    "Forecast",
    "HuntStyle",
    "InvalidTickerError",
    "Period",
    "PriceBar",
    "RatingTone",
    "SuggestionReport",
    "TickerId",
    "TickerStatus",
    "TrackedTicker",
    "TrapStats",
    "hunt_checks",
    "hunt_factors",
    "hunt_score",
    "parse_ticker",
    "rating_label",
    "shift_trading_days",
]
