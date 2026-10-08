"""Result of crawling one ticker."""

from dataclasses import dataclass

from livestocks.domain import Extras, Forecast, PriceBar


@dataclass(frozen=True, slots=True)
class CrawlResult:
    """Forecast (always present) plus best-effort price history and extras with their failure notes."""

    forecast: Forecast
    prices: tuple[PriceBar, ...] | None = None
    extras: Extras | None = None
    prices_error: str | None = None
    extras_error: str | None = None
