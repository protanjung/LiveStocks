"""Mapping of domain and service exceptions to HTTP error answers.
Every handler returns the shared ErrorResponse body with a stable machine-readable code.
register_error_handlers installs them on a FastAPI application.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from livestocks.api.models import ErrorResponse
from livestocks.domain import InvalidTickerError
from livestocks.services import (
    CrawlTimeoutError,
    TickerNotFoundError,
    UpstreamUnavailableError,
)

# exception type -> (HTTP status, error code)
ERROR_ANSWERS: dict[type[Exception], tuple[int, str]] = {
    InvalidTickerError: (422, "invalid_ticker"),
    TickerNotFoundError: (404, "ticker_not_found"),
    UpstreamUnavailableError: (502, "upstream_error"),
    CrawlTimeoutError: (504, "crawl_timeout"),
}


def register_error_handlers(app: FastAPI) -> None:
    """Install one exception handler per entry of ERROR_ANSWERS on the application.
    Each turns the exception into the matching status code and an ErrorResponse body.
    Unlisted exceptions keep FastAPI's default 500 handling.
    """
    for exception_type, (status_code, code) in ERROR_ANSWERS.items():
        app.add_exception_handler(exception_type, _handler(status_code, code))


def _handler(status_code: int, code: str):
    async def handle(_request: Request, exc: Exception) -> JSONResponse:
        body = ErrorResponse(code=code, detail=str(exc))
        return JSONResponse(status_code=status_code, content=body.model_dump())

    return handle
