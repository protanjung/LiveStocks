"""EPS / revenue history and analyst rating counts from TradingView's quote websocket.
The forecast page loads them client-side over wss://data.tradingview.com.
An anonymous quote session streams every field (~250KB) and ends with quote_completed.
"""

import asyncio
import json
import re
import time
from collections.abc import Sequence
from itertools import zip_longest
from typing import Any

import websockets

from livestocks.crawler.errors import UpstreamError
from livestocks.crawler.json_values import as_dict, as_float, as_int, as_list
from livestocks.domain import Dividend, DividendPayment, Extras, Period

WS_URL = "wss://data.tradingview.com/socket.io/websocket?from=symbols%2F{exchange}-{symbol}%2Fforecast-actuals-and-estimates%2F"
ORIGIN = "https://www.tradingview.com"
ANNUAL_KEEP, QUARTER_KEEP = (
    11,
    16,
)  # periods shown per chart, counting back from the last one with data
DIVIDEND_KEEP = 12  # past dividends kept, newest first


def _frame(method: str, params: list[Any]) -> str:
    body = json.dumps({"m": method, "p": params}, separators=(",", ":"))
    return f"~m~{len(body)}~m~{body}"


def _split(raw: str) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(raw):
        m = re.match(r"~m~(\d+)~m~", raw[i:])
        if not m:
            break
        start = i + m.end()
        out.append(raw[start : start + int(m.group(1))])
        i = start + int(m.group(1))
    return out


async def fetch_quote(
    exchange: str,
    symbol: str,
    max_seconds: float = 25.0,
    fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Open an anonymous TradingView quote session and collect the fields of a symbol.
    With fields None every field is streamed (about 200 KB); a short list is much lighter.
    Raises UpstreamError on socket errors, a bad status or an empty answer.
    """
    full = f"{exchange}:{symbol}"
    session = "qs_livestocks"
    collected: dict[str, Any] = {}
    deadline = time.monotonic() + max_seconds
    try:
        async with websockets.connect(
            WS_URL.format(exchange=exchange, symbol=symbol),
            additional_headers={"Origin": ORIGIN},
            max_size=None,
            open_timeout=10,
        ) as ws:
            setup: list[tuple[str, list[Any]]] = [
                ("set_data_quality", ["low"]),
                ("set_auth_token", ["unauthorized_user_token"]),
                ("set_locale", ["en", "US"]),
                ("quote_create_session", [session]),
            ]
            if fields:
                setup.append(("quote_set_fields", [session, *fields]))
            setup += [
                ("quote_add_symbols", [session, full]),
                ("quote_fast_symbols", [session, full]),
            ]
            for method, params in setup:
                await ws.send(_frame(method, params))
            done = False
            while not done:
                raw = await asyncio.wait_for(ws.recv(), max(0.1, deadline - time.monotonic()))
                for msg in _split(str(raw)):
                    if msg.startswith("~h~"):  # heartbeat: echo it back
                        await ws.send(f"~m~{len(msg)}~m~{msg}")
                        continue
                    try:
                        data = json.loads(msg)
                    except json.JSONDecodeError:
                        continue
                    if data.get("m") == "qsd":
                        q = data["p"][1]
                        if q.get("s") == "ok":
                            collected.update(q.get("v") or {})
                        else:
                            raise UpstreamError(f"quote status {q.get('s')}")
                    elif data.get("m") == "quote_completed":
                        done = True
    except UpstreamError:
        raise
    except (TimeoutError, OSError, websockets.WebSocketException) as e:
        raise UpstreamError(f"websocket error: {e.__class__.__name__}") from e
    if not collected:
        raise UpstreamError("no quote data")
    return collected


def _periods(raw: Any, keep: int) -> tuple[Period, ...]:
    out: list[Period] = []
    for raw_item in as_list(raw) or []:
        item = as_dict(raw_item)
        if item is None or not item.get("FiscalPeriod"):
            continue
        actual, est = as_float(item.get("Actual")), as_float(item.get("Estimate"))
        if actual is None and est is None:
            continue
        out.append(Period(str(item["FiscalPeriod"]), actual, est, bool(item.get("IsReported"))))
    return tuple(out[-keep:])


def _cell(rows: list[tuple[Any, ...]], index: int, column: int) -> Any:
    """Return one cell of the index-aligned history rows, or None when the row does not exist."""
    return rows[index][column] if index < len(rows) else None


def _dividend(v: dict[str, Any]) -> Dividend | None:
    """Extract the upcoming and recent dividend, their Recording Dates and the payment history.
    The *_h arrays are index-aligned and newest first. Index 0 is the upcoming dividend when one
    is announced, so the recent dividend is then at index 1.
    Returns None when the feed carries no dividend data for the ticker.
    """
    rows = list(
        zip_longest(
            as_list(v.get("dividend_ex_date_h")) or [],
            as_list(v.get("dividend_payment_date_h")) or [],
            as_list(v.get("dividend_amount_h")) or [],
            as_list(v.get("dividend_type_h")) or [],
            as_list(v.get("dividend_record_date_h")) or [],
        )
    )
    history = tuple(
        DividendPayment(
            as_int(ex),
            as_int(pay),
            as_float(amount),
            kind if isinstance(kind, str) else None,
            as_int(record),
        )
        for ex, pay, amount, kind, record in rows
        if as_int(ex) is not None or as_int(pay) is not None
    )[:DIVIDEND_KEEP]
    next_ex = as_int(v.get("dividend_ex_date_upcoming"))
    recent_at = 1 if next_ex is not None else 0
    last_ex = as_int(v.get("dividend_ex_date_recent"))
    yield_pct = as_float(v.get("dividends_yield_current"))
    if not history and last_ex is None and yield_pct is None:
        return None
    return Dividend(
        next_ex=next_ex,
        next_pay=as_int(v.get("dividend_payment_date_upcoming")),
        next_amount=as_float(v.get("dividend_amount_upcoming")),
        last_ex=last_ex,
        last_pay=as_int(v.get("dividend_payment_date_recent")),
        last_amount=as_float(v.get("dividend_amount_recent")),
        yield_pct=yield_pct,
        history=history,
        next_record=as_int(_cell(rows, 0, 4)) if next_ex is not None else None,
        last_record=as_int(_cell(rows, recent_at, 4)),
    )


def parse_quote(v: dict[str, Any]) -> Extras:
    """Extract rating counts, EPS/revenue series and dividends from raw quote fields.
    Missing fields become None or empty tuples instead of raising.
    Series are trimmed to the periods the charts show.
    """
    return Extras(
        strong_buy=as_int(v.get("recommendation_buy")),
        buy=as_int(v.get("recommendation_over")),
        hold=as_int(v.get("recommendation_hold")),
        sell=as_int(v.get("recommendation_under")),
        strong_sell=as_int(v.get("recommendation_sell")),
        eps_fy=_periods(v.get("earnings_fy_h"), ANNUAL_KEEP),
        eps_fq=_periods(v.get("earnings_fq_h"), QUARTER_KEEP),
        rev_fy=_periods(v.get("revenues_fy_h"), ANNUAL_KEEP),
        rev_fq=_periods(v.get("revenues_fq_h"), QUARTER_KEEP),
        dividend=_dividend(v),
    )


async def fetch_extras(exchange: str, symbol: str) -> Extras:
    """Fetch and parse the rating counts and EPS/revenue estimates of a ticker.
    Combines fetch_quote and parse_quote.
    Raises UpstreamError when the websocket session fails.
    """
    return parse_quote(await fetch_quote(exchange, symbol))
