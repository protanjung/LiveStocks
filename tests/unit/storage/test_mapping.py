import pytest

from livestocks.crawler.quote_stream import parse_quote
from livestocks.domain import ErrorKind
from livestocks.storage.mapping import (
    extras_from_json,
    extras_to_json,
    forecast_from_row,
    forecast_to_row,
    tracked_from_rows,
)
from livestocks.storage.models import TickerTable


class TestForecastMapping:
    def test_round_trips_every_field(self, make_forecast):
        forecast = make_forecast(price=2310.5)

        assert forecast_from_row(forecast_to_row(forecast, fetched_at=9)) == forecast

    def test_row_carries_the_fetch_time_and_no_id_yet(self, make_forecast):
        row = forecast_to_row(make_forecast(), fetched_at=9)

        assert row.fetched_at == 9
        assert row.id is None


class TestExtrasMapping:
    def test_round_trips_through_json(self, quote_data):
        extras = parse_quote(quote_data)

        assert extras_from_json(extras_to_json(extras)) == extras

    def test_wrong_shape_raises(self):
        with pytest.raises((KeyError, TypeError)):
            extras_from_json('{"strong_buy": 1}')


class TestTrackedMapping:
    def test_ticker_without_a_snapshot_has_no_forecast(self):
        ticker = TickerTable(
            exchange="IDX", symbol="X", added_at=1, last_error="boom", error_kind="upstream"
        )

        tracked = tracked_from_rows(ticker, None)

        assert tracked.forecast is None
        assert tracked.fetched_at is None
        assert tracked.error_kind is ErrorKind.UPSTREAM

    def test_snapshot_name_wins_over_the_ticker_name(self, make_forecast):
        ticker = TickerTable(exchange="IDX", symbol="TLKM", added_at=1, name="old")
        row = forecast_to_row(make_forecast(name="Telkom"), fetched_at=5)

        tracked = tracked_from_rows(ticker, row)

        assert tracked.name == "Telkom"
        assert tracked.fetched_at == 5
