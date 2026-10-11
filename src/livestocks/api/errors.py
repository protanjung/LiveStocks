"""Mapping of domain and service exceptions to HTTP error answers.
Every handler returns the shared ErrorResponse body with a stable machine-readable code.
register_error_handlers installs them on a FastAPI application.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from livestocks.api.models import ErrorResponse
from livestocks.domain import InvalidTickerError
from livestocks.services import (
    CrawlTimeoutError,
    SuggestionNotFoundError,
    TickerNotFoundError,
    UpstreamUnavailableError,
)


class UnauthorizedError(Exception):
    """The request carried no valid bearer token for a protected endpoint.
    Raised by the token check of the suggestion routes.
    Answered with 401 and the code unauthorized.
    """


class IngestDisabledError(Exception):
    """Suggestions cannot be delivered because no API token is configured on the server.
    Set LIVESTOCKS_API_TOKEN to enable the endpoint.
    Answered with 503 and the code ingest_disabled.
    """


class InvalidDateError(Exception):
    """The date in the URL is not a calendar date in YYYY-MM-DD form.
    Raised by the by-date suggestion route.
    Answered with 422 and the code invalid_date.
    """


# exception type -> (HTTP status, error code)
ERROR_ANSWERS: dict[type[Exception], tuple[int, str]] = {
    InvalidTickerError: (422, "invalid_ticker"),
    TickerNotFoundError: (404, "ticker_not_found"),
    UpstreamUnavailableError: (502, "upstream_error"),
    CrawlTimeoutError: (504, "crawl_timeout"),
    SuggestionNotFoundError: (404, "suggestion_not_found"),
    UnauthorizedError: (401, "unauthorized"),
    IngestDisabledError: (503, "ingest_disabled"),
    InvalidDateError: (422, "invalid_date"),
}

MAX_PROBLEMS = 5


def register_error_handlers(app: FastAPI) -> None:
    """Install one exception handler per entry of ERROR_ANSWERS on the application.
    Each turns the exception into the matching status code and an ErrorResponse body.
    Request validation errors become invalid_payload; other exceptions keep FastAPI's 500.
    """
    for exception_type, (status_code, code) in ERROR_ANSWERS.items():
        app.add_exception_handler(exception_type, _handler(status_code, code))
    app.add_exception_handler(RequestValidationError, _validation_handler)


def _handler(status_code: int, code: str):
    async def handle(_request: Request, exc: Exception) -> JSONResponse:
        body = ErrorResponse(code=code, detail=str(exc))
        return JSONResponse(status_code=status_code, content=body.model_dump())

    return handle


async def _validation_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    problems = [
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()[:MAX_PROBLEMS]
    ]
    body = ErrorResponse(code="invalid_payload", detail="; ".join(problems))
    return JSONResponse(status_code=422, content=body.model_dump())
