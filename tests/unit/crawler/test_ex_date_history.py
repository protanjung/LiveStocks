from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from livestocks.crawler import UpstreamError
from livestocks.crawler.ex_date_history import (
    KEEP_EVENTS,
    compute_ex_events,
    fetch_trap_stats,
    parse_dividends,
)
from livestocks.domain import PriceBar

START = datetime(2026, 1, 5, 2, 0, tzinfo=UTC)


def _ts(day: int) -> int:
    return int((START + timedelta(days=day)).timestamp())


def _bars(closes: list[float]) -> list[PriceBar]:
    return [PriceBar(_ts(i), c) for i, c in enumerate(closes)]


class TestComputeExEvents:
    def test_drop_is_measured_between_the_cum_and_the_ex_close(self):
        bars = _bars([100, 100, 100, 100, 100, 96, 97, 98, 99, 100, 101])

        (event,) = compute_ex_events(bars, {_ts(5): 2.0})

        assert (event.cum_close, event.ex_close) == (100, 96)
        assert event.is_trap

    def test_price_back_at_the_cum_close_counts_the_recovery_days(self):
        bars = _bars([100, 100, 100, 100, 100, 96, 97, 98, 99, 100, 101])

        (event,) = compute_ex_events(bars, {_ts(5): 5.0})

        assert event.recover_days == 4
        assert not event.is_trap

    def test_price_that_never_recovers_has_no_recovery_days(self):
        bars = _bars([100] * 5 + [90] * 30)

        (event,) = compute_ex_events(bars, {_ts(5): 5.0})

        assert event.recover_days is None

    def test_a_rise_on_the_ex_date_recovers_at_once(self):
        bars = _bars([100, 100, 100, 100, 100, 103, 104])

        (event,) = compute_ex_events(bars, {_ts(5): 2.0})

        assert event.recover_days == 0

    def test_a_dividend_on_the_first_bar_is_skipped_for_lack_of_a_cum_close(self):
        assert compute_ex_events(_bars([100, 99, 98]), {_ts(0): 1.0}) == ()

    def test_a_dividend_on_a_day_without_a_bar_is_skipped(self):
        assert compute_ex_events(_bars([100, 99, 98]), {_ts(40): 1.0}) == ()

    def test_zero_dividends_are_ignored(self):
        assert compute_ex_events(_bars([100, 99, 98]), {_ts(1): 0.0}) == ()

    def test_events_are_newest_first_and_capped(self):
        bars = _bars([100.0] * 60)
        dividends = {_ts(day): 1.0 for day in range(2, 40, 4)}

        events = compute_ex_events(bars, dividends)

        assert len(events) == KEEP_EVENTS
        assert events[0].ex_date > events[-1].ex_date


class TestParseDividends:
    def test_reads_amounts_by_ex_timestamp(self):
        data = {
            "chart": {"result": [{"events": {"dividends": {"1": {"amount": 2.5, "date": 1000}}}}]}
        }

        assert parse_dividends(data) == {1000: 2.5}

    def test_response_without_events_has_no_dividends(self):
        assert parse_dividends({"chart": {"result": [{}]}}) == {}

    def test_response_without_a_result_raises(self):
        from livestocks.crawler import ParseError

        with pytest.raises(ParseError):
            parse_dividends({"chart": {"result": None}})


def _response(closes: list[float], dividends: dict[int, float]) -> dict:
    return {
        "chart": {
            "result": [
                {
                    "timestamp": [_ts(i) for i in range(len(closes))],
                    "indicators": {"quote": [{"close": closes}]},
                    "events": {
                        "dividends": {
                            str(t): {"amount": a, "date": t} for t, a in dividends.items()
                        }
                    },
                }
            ]
        }
    }


class TestFetchTrapStats:
    async def test_unsupported_exchange_returns_none_without_a_request(self):
        async with httpx.AsyncClient() as client:
            assert await fetch_trap_stats(client, "WAT", "X") is None

    @respx.mock
    async def test_summarises_the_ex_dates_in_the_response(self):
        closes = [100.0] * 5 + [96.0] + [100.0] * 10
        respx.get(url__regex=r".*finance/chart/SIDO\.JK.*").mock(
            return_value=httpx.Response(200, json=_response(closes, {_ts(5): 2.0}))
        )

        async with httpx.AsyncClient() as client:
            stats = await fetch_trap_stats(client, "IDX", "SIDO")

        assert stats is not None
        assert len(stats.events) == 1
        assert stats.events[0].is_trap

    @respx.mock
    async def test_requests_five_years_with_dividend_events(self):
        route = respx.get(url__regex=r".*finance/chart.*").mock(
            return_value=httpx.Response(200, json=_response([100.0] * 3, {}))
        )

        async with httpx.AsyncClient() as client:
            await fetch_trap_stats(client, "IDX", "SIDO")

        params = route.calls.last.request.url.params
        assert params["range"] == "5y"
        assert params["events"] == "div"

    @respx.mock
    async def test_a_symbol_with_no_dividends_has_no_stats(self):
        respx.get(url__regex=r".*finance/chart.*").mock(
            return_value=httpx.Response(200, json=_response([100.0] * 3, {}))
        )

        async with httpx.AsyncClient() as client:
            assert await fetch_trap_stats(client, "IDX", "SIDO") is None

    @respx.mock
    async def test_http_error_raises_upstream_error(self):
        respx.get(url__regex=r".*finance/chart.*").mock(return_value=httpx.Response(500))

        async with httpx.AsyncClient() as client:
            with pytest.raises(UpstreamError, match="500"):
                await fetch_trap_stats(client, "IDX", "SIDO")
