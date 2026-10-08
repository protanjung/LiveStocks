import re

_PART = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,14}$")


def parse_ticker(raw: str, default_exchange: str) -> tuple[str, str]:
    """'tlkm' -> ('IDX', 'TLKM'); 'nasdaq:aapl' -> ('NASDAQ', 'AAPL'). Raises ValueError if malformed."""
    text = raw.strip().upper()
    exchange, _, symbol = text.rpartition(":")
    if ":" in text and not exchange:
        raise ValueError(f"'{raw.strip()}' is not a valid ticker. Use TLKM or IDX:TLKM.")
    exchange = exchange or default_exchange.upper()
    if not _PART.match(exchange) or not _PART.match(symbol):
        raise ValueError(f"'{raw.strip()}' is not a valid ticker. Use TLKM or IDX:TLKM.")
    return exchange, symbol
