"""Fetch and parse TradingView's forecast page.
The page embeds its data as JSON in prs.init-data+json script blocks.
Their keys are hashed and change between deploys, so blocks are found by the keys inside.
"""

import json
import re
from typing import Any

import httpx

from livestocks.crawler.errors import NotFoundError, ParseError, UpstreamError
from livestocks.crawler.json_values import as_dict, as_float, as_int, as_list
from livestocks.crawler.retry import with_retries
from livestocks.domain import Forecast

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


def _find(obj: Any, key: str) -> Any:
    """Depth-first search for the first value stored under ``key``."""
    mapping = as_dict(obj)
    if mapping is not None:
        if key in mapping:
            return mapping[key]
        children: list[Any] = list(mapping.values())
    else:
        children = as_list(obj) or []
    for child in children:
        hit = _find(child, key)
        if hit is not None:
            return hit
    return None


def _var(variables: dict[str, Any], name: str) -> Any:
    entry = as_dict(variables.get(name)) or {}
    fields = as_list(entry.get("fields")) or []
    first = as_dict(fields[0]) if fields else None
    return first.get("value") if first else None


def parse_html(html: str, exchange: str, symbol: str) -> Forecast:
    """Parse the forecast page HTML into a Forecast for the given exchange and symbol.
    Data blocks are found by the keys they contain, not by their hashed names.
    Raises ParseError when neither the quotes block nor the FAQ block is present.
    """
    blocks: list[Any] = []
    for m in _SCRIPT.finditer(html):
        try:
            blocks.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            continue

    quotes = as_dict(_find(blocks, "initForecastQuotes"))
    faq = as_list(_find(blocks, "symbolFaqData"))
    if quotes is None and faq is None:
        raise ParseError("forecast data blocks not found in page")

    quotes = quotes or {}
    # symbolFaqData is a list of Q&A items, each carrying its own ``variables``; merge them all.
    variables: dict[str, Any] = {}
    for item in faq or []:
        item_variables = as_dict((as_dict(item) or {}).get("variables"))
        for k, v in (item_variables or {}).items():
            variables.setdefault(k, v)

    name = _var(variables, "symbol_instrument_name")
    if not name:
        name = (as_dict(_find(blocks, "meta")) or {}).get("title")

    return Forecast(
        exchange=exchange,
        symbol=symbol,
        name=name if isinstance(name, str) else None,
        price=as_float(_var(variables, "price")),
        change_pct=as_float(_var(variables, "change_percent")),
        pt_avg=as_float(quotes.get("price_target_average")),
        pt_high=as_float(_var(variables, "max_estimate_price")),
        pt_low=as_float(_var(variables, "min_estimate_price")),
        n_analysts=as_int(quotes.get("price_target_estimates_num")),
        rating_mark=as_float(quotes.get("recommendation_mark")),
        n_ratings=as_int(quotes.get("recommendation_total")),
        ath=as_float(_var(variables, "all_time_high_price")),
        next_earnings=as_int(_var(variables, "earnings_release_next_date")),
    )


async def fetch_forecast(
    client: httpx.AsyncClient, exchange: str, symbol: str, retries: int = 2
) -> Forecast:
    """Fetch the forecast page and parse it, retrying transient upstream failures.
    A 404 raises NotFoundError at once; other errors are retried with backoff
    up to `retries` extra times before UpstreamError is raised.
    """
    url = URL.format(exchange=exchange, symbol=symbol)

    async def attempt() -> Forecast:
        try:
            resp = await client.get(url, headers=HEADERS, follow_redirects=True)
        except httpx.HTTPError as e:
            raise UpstreamError(f"network error: {e.__class__.__name__}") from e
        if resp.status_code == 404:
            raise NotFoundError("not found on TradingView")
        if resp.status_code != 200:
            raise UpstreamError(f"HTTP {resp.status_code}")
        return parse_html(resp.text, exchange, symbol)

    return await with_retries(attempt, attempts=retries + 1)
