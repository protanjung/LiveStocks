"""How a stock's price behaved on its past Ex Dates, from Yahoo Finance's five-year daily chart.
One request returns the closes and the dividend events, so trap statistics need no second source.
Trap risk is judged from the last few Ex Dates: did the price fall by more than the dividend?
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

import httpx

from livestocks.crawler.errors import ParseError, UpstreamError
from livestocks.crawler.json_values import as_dict, as_float, as_int
from livestocks.crawler.price_history import URL, parse_chart, yahoo_symbol
from livestocks.crawler.retry import with_retries
from livestocks.domain import ExDateEvent, PriceBar, TrapStats

KEEP_EVENTS = 6  # the most recent Ex Dates that are summarised
RECOVER_WINDOW = 20  # trading days after the Ex Date to wait for the price to come back


def _day(ts: int) -> date:
    """Return the UTC calendar day of a timestamp, so a bar and a dividend on the same day match."""
    return datetime.fromtimestamp(ts, UTC).date()


def compute_ex_events(
    bars: Sequence[PriceBar], dividends: Mapping[int, float]
) -> tuple[ExDateEvent, ...]:
    """Turn daily closes and dividends (Ex timestamp to amount) into the last few Ex Date events.
    The cum close is the bar before the Ex Date; a dividend with no bar before it is skipped.
    Events are returned newest first, at most KEEP_EVENTS of them.
    """
    index = {_day(b.ts): i for i, b in enumerate(bars)}
    events: list[ExDateEvent] = []
    for ex_ts, amount in dividends.items():
        i = index.get(_day(ex_ts))
        if i is None or i < 1 or amount <= 0:
            continue
        cum_close, ex_close = bars[i - 1].close, bars[i].close
        recover: int | None = None
        for k in range(0, RECOVER_WINDOW + 1):
            if i + k < len(bars) and bars[i + k].close >= cum_close:
                recover = k
                break
        events.append(ExDateEvent(bars[i].ts, amount, cum_close, ex_close, recover))
    events.sort(key=lambda e: e.ex_date, reverse=True)
    return tuple(events[:KEEP_EVENTS])


def parse_dividends(data: dict[str, Any]) -> dict[int, float]:
    """Read the dividend events of a Yahoo chart response as {Ex timestamp: amount per share}.
    A response with no events gives an empty dict; unusable entries are skipped.
    Raises ParseError when the response has no chart result at all.
    """
    try:
        result = data["chart"]["result"][0]
    except (KeyError, IndexError, TypeError) as e:
        raise ParseError("unexpected chart response") from e
    events = as_dict((as_dict(result) or {}).get("events")) or {}
    listed = as_dict(events.get("dividends")) or {}
    out: dict[int, float] = {}
    for key, item in listed.items():
        info = as_dict(item)
        ts = as_int(info.get("date")) if info else as_int(key)
        amount = as_float(info.get("amount")) if info else None
        if ts is not None and amount is not None:
            out[ts] = amount
    return out


async def fetch_trap_stats(
    client: httpx.AsyncClient, exchange: str, symbol: str
) -> TrapStats | None:
    """Download five years of closes and dividends for a symbol and summarise its Ex Date behaviour.
    Returns None for an exchange Yahoo does not cover, or when the symbol has no dividends.
    Network and HTTP failures are retried once, then raise UpstreamError.
    """
    ysym = yahoo_symbol(exchange, symbol)
    if ysym is None:
        return None
    url = URL.format(symbol=ysym)

    async def attempt() -> TrapStats | None:
        try:
            resp = await client.get(
                url,
                params={"range": "5y", "interval": "1d", "events": "div"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
        except httpx.HTTPError as e:
            raise UpstreamError(f"ex date history network error: {e.__class__.__name__}") from e
        if resp.status_code != 200:
            raise UpstreamError(f"ex date history HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise ParseError("ex date history is not JSON") from e
        events = compute_ex_events(parse_chart(data), parse_dividends(data))
        return TrapStats(events) if events else None

    return await with_retries(attempt, attempts=2)
