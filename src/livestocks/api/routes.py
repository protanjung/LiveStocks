"""HTTP routes of the public API.
build_router creates the router for a given ForecastService so it can be mounted on any FastAPI app.
The only endpoint today is GET /forecast/{ticker}.
"""

from typing import Any

from fastapi import APIRouter

from livestocks.api.models import ErrorResponse, ForecastResponse
from livestocks.services import ForecastService

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "TradingView has no such ticker."},
    422: {"model": ErrorResponse, "description": "The ticker text is malformed."},
    502: {"model": ErrorResponse, "description": "TradingView failed or changed its format."},
    504: {"model": ErrorResponse, "description": "The first crawl did not finish in time."},
}

DESCRIPTION = (
    "Returns the stored analyst forecast for a ticker such as `TLKM` (default exchange) or "
    "`NASDAQ:AAPL`.\n\n"
    "If the ticker is not tracked yet it is added, and the request waits for its first crawl "
    "(up to the configured limit). Known tickers are answered at once from storage, with "
    "`stale` set when the data is older than twice the refresh interval."
)


def build_router(service: ForecastService) -> APIRouter:
    """Create the API router whose handlers call the given forecast service.
    Mount it with a prefix such as /api/v1 and register the error handlers on the app.
    The router holds no state of its own.
    """
    router = APIRouter(tags=["forecast"])

    @router.get(
        "/forecast/{ticker}",
        response_model=ForecastResponse,
        responses=ERROR_RESPONSES,
        summary="Get the analyst forecast for a ticker, tracking it if new",
        description=DESCRIPTION,
    )
    async def get_forecast(ticker: str) -> ForecastResponse:
        result = await service.get_or_track(ticker)
        return ForecastResponse.from_result(result)

    return router
