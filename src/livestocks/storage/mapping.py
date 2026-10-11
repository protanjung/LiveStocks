"""Conversions between SQLModel table rows and the domain dataclasses.
Keeping them here lets the store speak domain types while the rest of storage stays ORM-shaped.
Extras are serialised as JSON text because they are always read and written as one unit.
"""

import json
from dataclasses import asdict

from livestocks.domain import ErrorKind, Extras, Forecast, Period, SuggestionReport, TrackedTicker
from livestocks.storage.models import ForecastTable, SuggestionReportTable, TickerTable

_PERIOD_FIELDS = ("eps_fy", "eps_fq", "rev_fy", "rev_fq")


def forecast_from_row(row: ForecastTable) -> Forecast:
    """Build a Forecast from one stored snapshot row.
    The row's exchange and symbol are copied as they are.
    Missing values stay None.
    """
    return Forecast(
        exchange=row.exchange,
        symbol=row.symbol,
        name=row.name,
        price=row.price,
        change_pct=row.change_pct,
        pt_avg=row.pt_avg,
        pt_high=row.pt_high,
        pt_low=row.pt_low,
        n_analysts=row.n_analysts,
        rating_mark=row.rating_mark,
        n_ratings=row.n_ratings,
        ath=row.ath,
        next_earnings=row.next_earnings,
    )


def forecast_to_row(forecast: Forecast, fetched_at: int) -> ForecastTable:
    """Build a snapshot row from a Forecast crawled at fetched_at (unix seconds).
    The id is left empty so the database assigns it.
    It is the inverse of forecast_from_row apart from the timestamp.
    """
    return ForecastTable(
        exchange=forecast.exchange,
        symbol=forecast.symbol,
        fetched_at=fetched_at,
        name=forecast.name,
        price=forecast.price,
        change_pct=forecast.change_pct,
        pt_avg=forecast.pt_avg,
        pt_high=forecast.pt_high,
        pt_low=forecast.pt_low,
        n_analysts=forecast.n_analysts,
        rating_mark=forecast.rating_mark,
        n_ratings=forecast.n_ratings,
        ath=forecast.ath,
        next_earnings=forecast.next_earnings,
    )


def tracked_from_rows(ticker: TickerTable, latest: ForecastTable | None) -> TrackedTicker:
    """Join a ticker row with its latest forecast row into a TrackedTicker.
    latest is None for a ticker that has never been crawled successfully.
    The display name falls back to the ticker row when the snapshot has none.
    """
    return TrackedTicker(
        exchange=ticker.exchange,
        symbol=ticker.symbol,
        name=(latest.name if latest else None) or ticker.name,
        added_at=ticker.added_at,
        last_fetch=ticker.last_fetch,
        next_fetch=ticker.next_fetch,
        last_error=ticker.last_error,
        fail_count=ticker.fail_count,
        dead=ticker.dead,
        forecast=forecast_from_row(latest) if latest else None,
        fetched_at=latest.fetched_at if latest else None,
        error_kind=ErrorKind(ticker.error_kind) if ticker.error_kind else None,
    )


def extras_to_json(extras: Extras) -> str:
    """Serialise extras to the JSON text stored in the extras table.
    Nested periods become plain dictionaries.
    extras_from_json restores the dataclasses.
    """
    return json.dumps(asdict(extras))


def extras_from_json(text: str) -> Extras:
    """Rebuild Extras from the JSON text written by extras_to_json.
    Period lists come back as tuples of Period.
    Raises KeyError or TypeError if the stored text has a different shape.
    """
    data = json.loads(text)
    for name in _PERIOD_FIELDS:
        data[name] = tuple(Period(**period) for period in data[name])
    return Extras(**data)


def suggestion_from_row(row: SuggestionReportTable) -> SuggestionReport:
    """Build a SuggestionReport from one stored report row.
    The payload stays the JSON text it was saved as.
    Nothing is parsed here; the api layer validates it on the way out.
    """
    return SuggestionReport(
        date=row.date,
        generated_at=row.generated_at,
        received_at=row.received_at,
        payload=row.payload,
    )
