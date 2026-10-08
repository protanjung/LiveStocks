"""Crawl everything we know how to fetch for one ticker."""

import asyncio
import logging
from collections.abc import Awaitable
from typing import TypeVar

import httpx

from livestocks.crawler.forecast_page import fetch_forecast
from livestocks.crawler.models import CrawlResult
from livestocks.crawler.price_history import fetch_prices
from livestocks.crawler.quote_stream import fetch_extras

log = logging.getLogger(__name__)
T = TypeVar("T")


async def _best_effort(call: Awaitable[T], what: str, key: str) -> tuple[T | None, str | None]:
    """Await ``call``; on any failure return (None, message) so the forecast is never lost."""
    try:
        return await call, None
    except Exception as e:  # noqa: BLE001 - prices and extras are optional and must not fail the crawl
        log.warning("%s for %s unavailable: %s", what, key, e)
        return None, str(e) or e.__class__.__name__


async def crawl_ticker(client: httpx.AsyncClient, exchange: str, symbol: str) -> CrawlResult:
    """Fetch the forecast (required), then price history and EPS/revenue extras (best-effort, concurrent).
    Raises CrawlError if the forecast itself cannot be fetched.
    """
    key = f"{exchange}:{symbol}"
    forecast = await fetch_forecast(client, exchange, symbol)
    (bars, prices_error), (extras, extras_error) = await asyncio.gather(
        _best_effort(fetch_prices(client, exchange, symbol), "price history", key),
        _best_effort(fetch_extras(exchange, symbol), "extras", key),
    )
    return CrawlResult(
        forecast=forecast,
        prices=None if bars is None else tuple(bars),
        extras=extras,
        prices_error=prices_error,
        extras_error=extras_error,
    )
