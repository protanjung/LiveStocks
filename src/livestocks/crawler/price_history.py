"""Daily close history for the forecast chart, fetched from Yahoo Finance.
TradingView only serves price history over its websocket feed, so Yahoo's chart API is used.
Only exchanges with a known Yahoo suffix are supported; others simply get no history.
"""

from typing import Any

import httpx

from livestocks.crawler.errors import ParseError, UpstreamError
from livestocks.crawler.retry import with_retries
from livestocks.domain import PriceBar

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SUFFIX = {
    "IDX": ".JK",
    "NASDAQ": "",
    "NYSE": "",
    "AMEX": "",
    "NYSEARCA": "",
    "LSE": ".L",
    "TSX": ".TO",
    "HKEX": ".HK",
    "ASX": ".AX",
    "NSE": ".NS",
    "BSE": ".BO",
    "SGX": ".SI",
    "XETR": ".DE",
    "TSE": ".T",
    "SET": ".BK",
    "KRX": ".KS",
    "MYX": ".KL",
}


def yahoo_symbol(exchange: str, symbol: str) -> str | None:
    """Map an exchange and symbol to Yahoo Finance's ticker, or None if unsupported.
    IDX symbols get .JK, US exchanges need no suffix, and dots become dashes (BRK.B).
    The suffix table covers the exchanges both TradingView and Yahoo list.
    """
    suffix = SUFFIX.get(exchange.upper())
    if suffix is None:
        return None
    return symbol.replace(".", "-") if suffix == "" else symbol + suffix


def parse_chart(data: dict[str, Any]) -> list[PriceBar]:
    """Turn a Yahoo chart response into PriceBars, skipping bars with a null close.
    Raises ParseError when the response lacks timestamps or closes.
    Timestamps stay in unix seconds.
    """
    try:
        result = data["chart"]["result"][0]
        stamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError) as e:
        raise ParseError("unexpected chart response") from e
    return [
        PriceBar(int(t), float(c)) for t, c in zip(stamps, closes, strict=False) if c is not None
    ]


async def fetch_prices(
    client: httpx.AsyncClient, exchange: str, symbol: str, range_: str = "2y"
) -> list[PriceBar]:
    """Download daily closes for the last range_ (default two years) from Yahoo.
    Returns an empty list for exchanges without a Yahoo mapping.
    Network and HTTP failures are retried once, then raise UpstreamError.
    """
    ysym = yahoo_symbol(exchange, symbol)
    if ysym is None:
        return []
    url = URL.format(symbol=ysym)

    async def attempt() -> list[PriceBar]:
        try:
            resp = await client.get(
                url,
                params={"range": range_, "interval": "1d"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
        except httpx.HTTPError as e:
            raise UpstreamError(f"price history network error: {e.__class__.__name__}") from e
        if resp.status_code != 200:
            raise UpstreamError(f"price history HTTP {resp.status_code}")
        return parse_chart(resp.json())

    return await with_retries(attempt, attempts=2)
