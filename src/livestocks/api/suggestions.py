"""HTTP routes for the daily stock suggestions delivered by the scheduled routine.
POST stores a report; the GET routes read it back.
All of them check the bearer token from the settings, and POST refuses to run without one.
"""

import secrets
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query

from livestocks.api.errors import IngestDisabledError, InvalidDateError, UnauthorizedError
from livestocks.api.models import (
    ErrorResponse,
    SuggestionAccepted,
    SuggestionDay,
    SuggestionsPayload,
    SuggestionsResponse,
)
from livestocks.config import Settings
from livestocks.services import SuggestionService

READ_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "The bearer token is missing or wrong."},
    404: {"model": ErrorResponse, "description": "No report for that date, or none yet."},
}
POST_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "The bearer token is missing or wrong."},
    422: {"model": ErrorResponse, "description": "The body is not a valid idx-suggestions/v1."},
    503: {"model": ErrorResponse, "description": "The server has no LIVESTOCKS_API_TOKEN set."},
}


def build_suggestions_router(service: SuggestionService, settings: Settings) -> APIRouter:
    """Create the router for delivering and reading the daily suggestion reports.
    Mount it with the same prefix as the forecast router and register the error handlers.
    The token is read from settings on each request.
    """
    router = APIRouter(tags=["suggestions"])

    def token_matches(authorization: str | None) -> bool:
        scheme, _, token = (authorization or "").partition(" ")
        supplied = token.strip() if scheme.lower() == "bearer" else ""
        return secrets.compare_digest(supplied.encode(), (settings.api_token or "").encode())

    def require_read(authorization: Annotated[str | None, Header()] = None) -> None:
        if settings.api_token and not token_matches(authorization):
            raise UnauthorizedError("a valid bearer token is required")

    def require_write(authorization: Annotated[str | None, Header()] = None) -> None:
        if not settings.api_token:
            raise IngestDisabledError("set LIVESTOCKS_API_TOKEN on the server to accept reports")
        if not token_matches(authorization):
            raise UnauthorizedError("a valid bearer token is required")

    @router.post(
        "/suggestions",
        status_code=201,
        response_model=SuggestionAccepted,
        responses=POST_ERRORS,
        dependencies=[Depends(require_write)],
        summary="Deliver the day's stock suggestions",
        description=(
            "Stores an `idx-suggestions/v1` document, replacing any report already stored for "
            "its `date`. Send `Authorization: Bearer <LIVESTOCKS_API_TOKEN>`."
        ),
    )
    async def post_suggestions(payload: SuggestionsPayload) -> SuggestionAccepted:
        report = await service.save(
            payload.date.isoformat(),
            payload.generated_at.isoformat(),
            payload.model_dump_json(by_alias=True),
        )
        return SuggestionAccepted(
            date=payload.date,
            received_at=datetime.fromtimestamp(report.received_at, UTC),
            count=len(payload.suggestions),
        )

    @router.get(
        "/suggestions/latest",
        response_model=SuggestionsResponse,
        responses=READ_ERRORS,
        dependencies=[Depends(require_read)],
        summary="Get the newest stock suggestions",
        description="Returns the report with the newest trading date.",
    )
    async def get_latest() -> SuggestionsResponse:
        return SuggestionsResponse.from_report(await service.latest())

    @router.get(
        "/suggestions/{day}",
        response_model=SuggestionsResponse,
        responses={**READ_ERRORS, 422: {"model": ErrorResponse, "description": "Bad date."}},
        dependencies=[Depends(require_read)],
        summary="Get the stock suggestions of one trading date",
        description="`day` is a date in `YYYY-MM-DD` form.",
    )
    async def get_day(day: str) -> SuggestionsResponse:
        try:
            parsed = date.fromisoformat(day)
        except ValueError:
            raise InvalidDateError(f"{day!r} is not a date in YYYY-MM-DD form") from None
        return SuggestionsResponse.from_report(await service.get(parsed.isoformat()))

    @router.get(
        "/suggestions",
        response_model=list[SuggestionDay],
        responses={401: READ_ERRORS[401]},
        dependencies=[Depends(require_read)],
        summary="List the trading dates that have suggestions",
        description="Newest first, with the count of BUY, SELL and HOLD rows of each date.",
    )
    async def list_days(limit: Annotated[int, Query(ge=1, le=365)] = 30) -> list[SuggestionDay]:
        return [SuggestionDay.from_report(r) for r in await service.recent(limit)]

    return router
