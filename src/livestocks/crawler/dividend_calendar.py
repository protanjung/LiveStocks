"""Market-wide dividend calendar from TradingView's scanner endpoint, one request per market.
Two scans run per exchange: announced ex-dates still ahead, and ex-dates in the last RECENT_DAYS.
Rows are merged by symbol, preferring the announced dividend, and classified by where they stand.
"""

import asyncio
import time
from dataclasses import replace
from typing import Any

import httpx
from loguru import logger

from livestocks.crawler.errors import ParseError, UpstreamError
from livestocks.crawler.json_values import as_dict, as_float, as_int, as_list
from livestocks.crawler.quote_stream import fetch_quote, parse_quote
from livestocks.crawler.retry import with_retries
from livestocks.domain import CalendarEntry, CalendarKind, shift_trading_days

SCAN_URL = "https://scanner.tradingview.com/{market}/scan"
RECENT_DAYS = 30
ROWS = 200  # scanner rows per request; one market rarely has more dividends than this
RECORD_LOOKUPS = 5  # websocket sessions open at once when reading Recording Dates
RECORD_FIELDS = ("dividend_ex_date_h", "dividend_record_date_h")  # all a lookup needs
COLUMNS = (
    "name",
    "description",
    "dividend_ex_date_upcoming",
    "dividend_payment_date_upcoming",
    "dividend_amount_upcoming",
    "dividend_ex_date_recent",
    "dividend_payment_date_recent",
    "dividend_amount_recent",
    "dividends_yield_current",
    "close",
    "change",
    "average_volume_30d_calc",
    "sector",
    "dividend_payout_ratio_ttm",
    "dividend_payout_ratio_fy",
    "continuous_dividend_payout",
    "continuous_dividend_growth",
    "cash_dividend_coverage_ratio_ttm",
    "dividends_yield",
)
REQUIRED_COLUMNS = 9  # the dividend dates and amounts; the fundamentals after them are optional
MARKETS = {
    "IDX": "indonesia",
    "NASDAQ": "america",
    "NYSE": "america",
    "AMEX": "america",
    "NYSEARCA": "america",
    "LSE": "uk",
    "TSX": "canada",
    "HKEX": "hongkong",
    "ASX": "australia",
    "NSE": "india",
    "BSE": "india",
    "SGX": "singapore",
    "XETR": "germany",
    "TSE": "japan",
    "SET": "thailand",
    "KRX": "korea",
    "MYX": "malaysia",
}


def scanner_market(exchange: str) -> str | None:
    """Return the scanner market name for a TradingView exchange, or None if unsupported.
    Several exchanges share a market, such as the US exchanges under america.
    Rows are filtered by exchange afterwards, so a shared market never leaks other listings.
    """
    return MARKETS.get(exchange.upper())


def _text(value: Any) -> str | None:
    """Return value if it is a string, else None.
    Scanner names come back as plain strings or null.
    """
    return value if isinstance(value, str) else None


def _cell(values: list[Any], index: int) -> Any:
    """Return one scanner value, or None when the row is shorter than the column list."""
    return values[index] if index < len(values) else None


def _fundamentals(values: list[Any]) -> dict[str, Any]:
    """Read the optional price, volume, payout and streak columns of one scanner row.
    The annual yield is the current yield, or the plain yield when the current one is 0 or missing.
    The payout ratio is the trailing figure, or the fiscal-year one when that is 0.
    """
    now, plain = as_float(_cell(values, 8)), as_float(_cell(values, 18))
    ttm, fy = as_float(_cell(values, 13)), as_float(_cell(values, 14))
    return {
        "yield_pct": now or plain or None,
        "price": as_float(_cell(values, 9)),
        "change_pct": as_float(_cell(values, 10)),
        "avg_volume": as_float(_cell(values, 11)),
        "sector": _text(_cell(values, 12)),
        "payout": ttm or fy or None,
        "streak_years": as_int(_cell(values, 15)),
        "growth_years": as_int(_cell(values, 16)),
        "coverage": as_float(_cell(values, 17)),
    }


def _entry(exchange: str, symbol: str, values: list[Any], now: int) -> CalendarEntry | None:
    """Build one calendar row, preferring the announced dividend over the most recent one.
    Returns None when the row has neither an upcoming nor a recent ex-date.
    The fundamentals come from the optional columns after the dividend dates.
    """
    name = _text(values[1]) or _text(values[0])
    fund = _fundamentals(values)
    yield_pct = fund.pop("yield_pct")
    ex_up = as_int(values[2])
    if ex_up is not None and ex_up >= now:
        return CalendarEntry(
            exchange,
            symbol,
            name,
            ex_up,
            as_int(values[3]),
            as_float(values[4]),
            yield_pct,
            CalendarKind.UPCOMING,
            **fund,
        )
    ex_rec = as_int(values[5])
    if ex_rec is None:
        return None
    pay_rec = as_int(values[6])
    kind = CalendarKind.PAYING if pay_rec is not None and pay_rec >= now else CalendarKind.RECENT
    return CalendarEntry(
        exchange, symbol, name, ex_rec, pay_rec, as_float(values[7]), yield_pct, kind, **fund
    )


def _with_derived_dates(entry: CalendarEntry) -> CalendarEntry:
    """Fill the Cum Date and a derived Recording Date from the Ex Date.
    The Cum Date is the last trading day before the Ex Date.
    The Recording Date is the first trading day after it.
    Both skip weekends only, so they are approximations until the real Recording Date is read.
    """
    if entry.ex_date is None:
        return entry
    return replace(
        entry,
        cum_date=shift_trading_days(entry.ex_date, -1),
        record_date=shift_trading_days(entry.ex_date, 1),
    )


def _record_for(raw: dict[str, Any], ex_date: int | None) -> int | None:
    """Return the Recording Date TradingView publishes for one Ex Date, or None when it has none."""
    dividend = parse_quote(raw).dividend
    if dividend is None or ex_date is None:
        return None
    for payment in dividend.history:
        if payment.ex_date == ex_date and payment.record_date is not None:
            return payment.record_date
    return None


async def _with_record_dates(entries: list[CalendarEntry]) -> list[CalendarEntry]:
    """Replace each derived Recording Date with the one TradingView publishes for the same Ex Date.
    Each symbol needs one short websocket session, and at most RECORD_LOOKUPS run at once.
    A symbol whose lookup fails, or whose feed has no matching Ex Date, keeps the derived date.
    """
    gate = asyncio.Semaphore(RECORD_LOOKUPS)

    async def one(entry: CalendarEntry) -> CalendarEntry:
        async with gate:
            try:
                raw = await fetch_quote(
                    entry.exchange, entry.symbol, max_seconds=15.0, fields=RECORD_FIELDS
                )
            except UpstreamError as e:
                logger.debug("recording date unavailable for {}: {}", entry.symbol, e)
                return entry
        record = _record_for(raw, entry.ex_date)
        return entry if record is None else replace(entry, record_date=record, record_real=True)

    return list(await asyncio.gather(*(one(e) for e in entries)))


def parse_scan(data: Any, exchange: str, now: int) -> list[CalendarEntry]:
    """Turn a scanner response into calendar rows for one exchange.
    Rows of other exchanges in the same market are skipped, as are rows with no dividend dates.
    Raises ParseError when the response has no data array.
    """
    root = as_dict(data)
    rows = as_list(root.get("data")) if root is not None else None
    if rows is None:
        raise ParseError("unexpected scanner response")
    prefix = f"{exchange}:"
    entries: list[CalendarEntry] = []
    for raw in rows:
        item = as_dict(raw)
        ref = _text(item.get("s")) if item is not None else None
        values = as_list(item.get("d")) if item is not None else None
        if ref is None or values is None or len(values) < REQUIRED_COLUMNS:
            continue
        if not ref.startswith(prefix):
            continue
        entry = _entry(exchange, ref.removeprefix(prefix), values, now)
        if entry is not None:
            entries.append(_with_derived_dates(entry))
    return entries


async def _scan(
    client: httpx.AsyncClient,
    market: str,
    exchange: str,
    body: dict[str, Any],
    now: int,
) -> list[CalendarEntry]:
    """Run one scanner request and parse it, retrying transient network failures once.
    Network and HTTP failures raise UpstreamError; a malformed body raises ParseError.
    """
    url = SCAN_URL.format(market=market)

    async def attempt() -> list[CalendarEntry]:
        try:
            resp = await client.post(url, json=body, headers={"User-Agent": "Mozilla/5.0"})
        except httpx.HTTPError as e:
            raise UpstreamError(f"dividend calendar network error: {e.__class__.__name__}") from e
        if resp.status_code != 200:
            raise UpstreamError(f"dividend calendar HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise ParseError("dividend calendar is not JSON") from e
        return parse_scan(data, exchange, now)

    return await with_retries(attempt, attempts=2)


async def fetch_calendar(
    client: httpx.AsyncClient, exchange: str, now: int | None = None
) -> list[CalendarEntry]:
    """Return the dividend calendar of an exchange, one row per symbol.
    Announced ex-dates and ex-dates from the last RECENT_DAYS are fetched concurrently and merged.
    Returns an empty list for exchanges without a scanner market.
    """
    market = scanner_market(exchange)
    if market is None:
        return []
    current = int(time.time()) if now is None else now
    since = current - RECENT_DAYS * 86400
    upcoming_body: dict[str, Any] = {
        "filter": [{"left": "dividend_ex_date_upcoming", "operation": "nempty"}],
        "columns": list(COLUMNS),
        "sort": {"sortBy": "dividend_ex_date_upcoming", "sortOrder": "asc"},
        "range": [0, ROWS],
    }
    recent_body: dict[str, Any] = {
        "filter": [{"left": "dividend_ex_date_recent", "operation": "greater", "right": since}],
        "columns": list(COLUMNS),
        "sort": {"sortBy": "dividend_ex_date_recent", "sortOrder": "desc"},
        "range": [0, ROWS],
    }
    upcoming, recent = await asyncio.gather(
        _scan(client, market, exchange, upcoming_body, current),
        _scan(client, market, exchange, recent_body, current),
    )
    merged: dict[str, CalendarEntry] = {}
    for entry in [*upcoming, *recent]:
        held = merged.get(entry.symbol)
        if held is None or (
            entry.kind is CalendarKind.UPCOMING and held.kind is not CalendarKind.UPCOMING
        ):
            merged[entry.symbol] = entry
    return await _with_record_dates(list(merged.values()))
