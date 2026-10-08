"""Result of crawling one ticker.
The forecast is mandatory; price history and extras are best-effort.
A failed optional part is recorded as an error string instead of raised.
"""

from dataclasses import dataclass

from livestocks.domain import Extras, Forecast, PriceBar


@dataclass(frozen=True, slots=True)
class CrawlResult:
    """Forecast plus optional price history and extras from one crawl.
    prices and extras are None when their fetch failed or was skipped.
    prices_error and extras_error then hold the reason.
    """

    forecast: Forecast
    prices: tuple[PriceBar, ...] | None = None
    extras: Extras | None = None
    prices_error: str | None = None
    extras_error: str | None = None
