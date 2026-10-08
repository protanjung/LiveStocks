"""Fetch and parse TradingView's forecast page.

The page embeds its data as JSON in ``<script type="application/prs.init-data+json">`` blocks. The top-level
keys are hashed and change between deploys, so blocks are located by the keys they contain instead.
"""

import asyncio
import json
import re
from typing import Any

import httpx

from .models import Forecast

URL = "https://www.tradingview.com/symbols/{exchange}-{symbol}/forecast-price-target/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
_SCRIPT = re.compile(r'<script type="application/prs\.init-data\+json">(.*?)</script>', re.S)


class ScrapeError(Exception):
    """Transient failure (network, rate limit, server error). Worth retrying."""


class NotFoundError(ScrapeError):
    """Ticker does not exist on TradingView, or has no forecast page."""


class ParseError(ScrapeError):
    """Page loaded but expected data was missing; the page layout probably changed."""


def _find(obj: Any, key: str) -> Any:
    """Depth-first search for the first value stored under ``key``."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        children = obj.values()
    elif isinstance(obj, list):
        children = obj
    else:
        return None
    for child in children:
        hit = _find(child, key)
        if hit is not None:
            return hit
    return None


def _var(variables: dict[str, Any], name: str) -> Any:
    fields = (variables.get(name) or {}).get("fields") or []
    return fields[0].get("value") if fields else None


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _int(v: Any) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def parse_html(html: str, exchange: str, symbol: str) -> Forecast:
    blocks = []
    for m in _SCRIPT.finditer(html):
        try:
            blocks.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            continue

    quotes = _find(blocks, "initForecastQuotes")
    faq = _find(blocks, "symbolFaqData")
    if not isinstance(quotes, dict) and not isinstance(faq, list):
        raise ParseError("forecast data blocks not found in page")

    quotes = quotes if isinstance(quotes, dict) else {}
    # symbolFaqData is a list of Q&A items, each carrying its own ``variables``; merge them all.
    variables: dict[str, Any] = {}
    for item in faq if isinstance(faq, list) else []:
        if isinstance(item, dict) and isinstance(item.get("variables"), dict):
            for k, v in item["variables"].items():
                variables.setdefault(k, v)

    name = _var(variables, "symbol_instrument_name")
    if not name:
        meta = _find(blocks, "meta")
        name = meta.get("title") if isinstance(meta, dict) else None

    return Forecast(
        exchange=exchange,
        symbol=symbol,
        name=name,
        price=_num(_var(variables, "price")),
        change_pct=_num(_var(variables, "change_percent")),
        pt_avg=_num(quotes.get("price_target_average")),
        pt_high=_num(_var(variables, "max_estimate_price")),
        pt_low=_num(_var(variables, "min_estimate_price")),
        n_analysts=_int(quotes.get("price_target_estimates_num")),
        rating_mark=_num(quotes.get("recommendation_mark")),
        n_ratings=_int(quotes.get("recommendation_total")),
        ath=_num(_var(variables, "all_time_high_price")),
        next_earnings=_int(_var(variables, "earnings_release_next_date")),
    )


async def fetch_forecast(
    client: httpx.AsyncClient, exchange: str, symbol: str, retries: int = 2
) -> Forecast:
    url = URL.format(exchange=exchange, symbol=symbol)
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.get(url, headers=HEADERS, follow_redirects=True)
        except httpx.HTTPError as e:
            last = ScrapeError(f"network error: {e.__class__.__name__}")
        else:
            if resp.status_code == 404:
                raise NotFoundError("not found on TradingView")
            if resp.status_code == 200:
                return parse_html(resp.text, exchange, symbol)
            last = ScrapeError(f"HTTP {resp.status_code}")
        if attempt < retries:
            await asyncio.sleep(2**attempt * 2)
    assert last is not None
    raise last
