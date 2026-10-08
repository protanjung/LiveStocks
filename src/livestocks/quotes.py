"""EPS / revenue history and analyst rating counts from TradingView's quote websocket.

The forecast page loads these client-side over ``wss://data.tradingview.com``. An anonymous quote session for a
symbol streams every field (about 1,400, ~250KB) and ends with ``quote_completed``.
"""

import asyncio
import json
import re
import time
from typing import Any

import websockets

from .models import Extras, Period

WS_URL = "wss://data.tradingview.com/socket.io/websocket?from=symbols%2F{exchange}-{symbol}%2Fforecast-actuals-and-estimates%2F"
ORIGIN = "https://www.tradingview.com"
ANNUAL_KEEP, QUARTER_KEEP = 11, 16  # periods shown per chart, counting back from the last one with data


class QuoteError(Exception):
    pass


def _frame(method: str, params: list) -> str:
    body = json.dumps({"m": method, "p": params}, separators=(",", ":"))
    return f"~m~{len(body)}~m~{body}"


def _split(raw: str) -> list[str]:
    out, i = [], 0
    while i < len(raw):
        m = re.match(r"~m~(\d+)~m~", raw[i:])
        if not m:
            break
        start = i + m.end()
        out.append(raw[start : start + int(m.group(1))])
        i = start + int(m.group(1))
    return out


async def fetch_quote(exchange: str, symbol: str, timeout: float = 25.0) -> dict[str, Any]:
    full = f"{exchange}:{symbol}"
    session = "qs_livestocks"
    fields: dict[str, Any] = {}
    deadline = time.monotonic() + timeout
    try:
        async with websockets.connect(
            WS_URL.format(exchange=exchange, symbol=symbol),
            additional_headers={"Origin": ORIGIN},
            max_size=None,
            open_timeout=10,
        ) as ws:
            for method, params in (
                ("set_data_quality", ["low"]),
                ("set_auth_token", ["unauthorized_user_token"]),
                ("set_locale", ["en", "US"]),
                ("quote_create_session", [session]),
                ("quote_add_symbols", [session, full]),
                ("quote_fast_symbols", [session, full]),
            ):
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
                            fields.update(q.get("v") or {})
                        else:
                            raise QuoteError(f"quote status {q.get('s')}")
                    elif data.get("m") == "quote_completed":
                        done = True
    except QuoteError:
        raise
    except (asyncio.TimeoutError, OSError, websockets.WebSocketException) as e:
        raise QuoteError(f"websocket error: {e.__class__.__name__}") from e
    if not fields:
        raise QuoteError("no quote data")
    return fields


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _count(v: Any) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _periods(raw: Any, keep: int) -> tuple[Period, ...]:
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not item.get("FiscalPeriod"):
            continue
        actual, est = _num(item.get("Actual")), _num(item.get("Estimate"))
        if actual is None and est is None:
            continue
        out.append(Period(str(item["FiscalPeriod"]), actual, est, bool(item.get("IsReported"))))
    return tuple(out[-keep:])


def parse_quote(v: dict[str, Any]) -> Extras:
    return Extras(
        strong_buy=_count(v.get("recommendation_buy")),
        buy=_count(v.get("recommendation_over")),
        hold=_count(v.get("recommendation_hold")),
        sell=_count(v.get("recommendation_under")),
        strong_sell=_count(v.get("recommendation_sell")),
        eps_fy=_periods(v.get("earnings_fy_h"), ANNUAL_KEEP),
        eps_fq=_periods(v.get("earnings_fq_h"), QUARTER_KEEP),
        rev_fy=_periods(v.get("revenues_fy_h"), ANNUAL_KEEP),
        rev_fq=_periods(v.get("revenues_fq_h"), QUARTER_KEEP),
    )


async def fetch_extras(exchange: str, symbol: str) -> Extras:
    return parse_quote(await fetch_quote(exchange, symbol))
