"""Daily close history for the forecast chart.

TradingView only serves price history through its websocket feed, so closes come from Yahoo Finance's public
chart endpoint instead. Only exchanges with a known Yahoo suffix are supported; others get no history.
"""

import httpx

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SUFFIX = {
    "IDX": ".JK", "NASDAQ": "", "NYSE": "", "AMEX": "", "NYSEARCA": "", "LSE": ".L", "TSX": ".TO",
    "HKEX": ".HK", "ASX": ".AX", "NSE": ".NS", "BSE": ".BO", "SGX": ".SI", "XETR": ".DE", "TSE": ".T",
    "SET": ".BK", "KRX": ".KS", "MYX": ".KL",
}


class PriceError(Exception):
    pass


def yahoo_symbol(exchange: str, symbol: str) -> str | None:
    suffix = SUFFIX.get(exchange.upper())
    if suffix is None:
        return None
    return symbol.replace(".", "-") if suffix == "" else symbol + suffix


def parse_chart(data: dict) -> list[tuple[int, float]]:
    try:
        result = data["chart"]["result"][0]
        stamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError) as e:
        raise PriceError("unexpected chart response") from e
    return [(int(t), float(c)) for t, c in zip(stamps, closes) if c is not None]


async def fetch_prices(
    client: httpx.AsyncClient, exchange: str, symbol: str, range_: str = "2y"
) -> list[tuple[int, float]]:
    ysym = yahoo_symbol(exchange, symbol)
    if ysym is None:
        return []
    try:
        resp = await client.get(
            URL.format(symbol=ysym),
            params={"range": range_, "interval": "1d"},
            headers={"User-Agent": "Mozilla/5.0"},
        )
    except httpx.HTTPError as e:
        raise PriceError(f"network error: {e.__class__.__name__}") from e
    if resp.status_code != 200:
        raise PriceError(f"HTTP {resp.status_code}")
    return parse_chart(resp.json())
