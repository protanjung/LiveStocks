"""Parsing of user-supplied ticker text.
Accepts a bare symbol or EXCHANGE:SYMBOL in any letter case.
Everything is normalised to upper case before it is stored or crawled.
"""

import re

from livestocks.domain.errors import InvalidTickerError
from livestocks.domain.models import TickerId

_PART = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,14}$")


def parse_ticker(raw: str, default_exchange: str) -> TickerId:
    """Parse 'tlkm' or 'nasdaq:aapl' into an upper-case TickerId.
    A bare symbol gets default_exchange.
    Raises InvalidTickerError for empty, malformed or oversized input.
    """
    text = raw.strip().upper()
    exchange, _, symbol = text.rpartition(":")
    if ":" in text and not exchange:
        raise _invalid(raw)
    exchange = exchange or default_exchange.upper()
    if not _PART.match(exchange) or not _PART.match(symbol):
        raise _invalid(raw)
    return TickerId(exchange, symbol)


def _invalid(raw: str) -> InvalidTickerError:
    return InvalidTickerError(f"'{raw.strip()}' is not a valid ticker. Use TLKM or IDX:TLKM.")
