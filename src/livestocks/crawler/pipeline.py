"""Crawl everything we know how to fetch for one ticker.
The forecast page is required; prices and extras are fetched concurrently after it.
Optional failures are logged and returned in the result instead of raised.
"""

import asyncio
from collections.abc import Awaitable

import httpx
from loguru import logger

from livestocks.crawler.forecast_page import fetch_forecast
from livestocks.crawler.models import CrawlResult
from livestocks.crawler.price_history import fetch_prices
from livestocks.crawler.quote_stream import fetch_extras


async def _best_effort[T](call: Awaitable[T], what: str, key: str) -> tuple[T | None, str | None]:
    """Await ``call``; on any failure return (None, message) so the forecast is never lost."""
    try:
        return await call, None
    except Exception as e:  # noqa: BLE001 - prices and extras are optional and must not fail the crawl
        logger.bind(ticker=key).warning("{} unavailable: {}", what, e)
        return None, str(e) or e.__class__.__name__


async def crawl_ticker(client: httpx.AsyncClient, exchange: str, symbol: str) -> CrawlResult:
    """Fetch the forecast, then price history and EPS/revenue extras concurrently.
    Raises CrawlError if the forecast itself cannot be fetched.
    Price or extras failures are returned inside the CrawlResult.
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
