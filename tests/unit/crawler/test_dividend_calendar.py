import asyncio
import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from livestocks.crawler import ParseError, UpstreamError, dividend_calendar
from livestocks.crawler.dividend_calendar import (
    _record_for,
    _with_derived_dates,
    fetch_calendar,
    parse_scan,
    scanner_market,
)
from livestocks.domain import CalendarEntry, CalendarKind, shift_trading_days

NOW = 1_790_000_000


@pytest.fixture(autouse=True)
def offline_quotes(monkeypatch):
    """Keep the websocket out of these tests.
    Each Recording Date lookup fails, so the derived dates are what the tests see.
    """

    async def unreachable(*args, **kwargs):
        raise UpstreamError("offline in tests")

    monkeypatch.setattr(dividend_calendar, "fetch_quote", unreachable)


SCAN_URL = "https://scanner.tradingview.com/indonesia/scan"


def _row(
    symbol: str,
    *,
    ex_up: int | None = None,
    pay_up: int | None = None,
    amt_up: float | None = None,
    ex_rec: int | None = None,
    pay_rec: int | None = None,
    amt_rec: float | None = None,
    yld: float | None = None,
) -> dict:
    values = [symbol, "PT Test Tbk", ex_up, pay_up, amt_up, ex_rec, pay_rec, amt_rec, yld]
    return {"s": f"IDX:{symbol}", "d": values}


def _scan(*rows: dict) -> dict:
    return {"totalCount": len(rows), "data": list(rows)}


class TestScannerMarket:
    def test_known_exchange_maps_to_its_market(self):
        assert scanner_market("idx") == "indonesia"

    def test_unknown_exchange_has_no_market(self):
        assert scanner_market("WAT") is None


class TestParseScan:
    def test_announced_dividend_is_upcoming(self):
        data = _scan(_row("SIDO", ex_up=NOW + 100, pay_up=NOW + 200, amt_up=10, yld=10.8))

        (entry,) = parse_scan(data, "IDX", NOW)

        assert entry.kind is CalendarKind.UPCOMING
        assert entry.ex_date == NOW + 100
        assert entry.pay_date == NOW + 200
        assert entry.amount == 10
        assert entry.yield_pct == pytest.approx(10.8)

    def test_passed_ex_date_with_payout_ahead_is_paying(self):
        data = _scan(_row("CSRA", ex_rec=NOW - 100, pay_rec=NOW + 100, amt_rec=15))

        (entry,) = parse_scan(data, "IDX", NOW)

        assert entry.kind is CalendarKind.PAYING

    def test_fully_paid_dividend_is_recent(self):
        data = _scan(_row("AMRT", ex_rec=NOW - 100, pay_rec=NOW - 50, amt_rec=5))

        (entry,) = parse_scan(data, "IDX", NOW)

        assert entry.kind is CalendarKind.RECENT

    def test_rows_of_other_exchanges_are_skipped(self):
        data = _scan({"s": "NYSE:XYZ", "d": ["XYZ", "x", None, None, None, NOW, None, 1, None]})

        assert parse_scan(data, "IDX", NOW) == []

    def test_rows_without_dividend_dates_are_skipped(self):
        assert parse_scan(_scan(_row("TLKM")), "IDX", NOW) == []

    def test_response_without_data_array_raises_parse_error(self):
        with pytest.raises(ParseError):
            parse_scan({"totalCount": 0}, "IDX", NOW)


class TestFetchCalendar:
    @respx.mock
    async def test_merges_both_scans_and_prefers_the_announced_dividend(self):
        upcoming = _scan(_row("SIDO", ex_up=NOW + 100, pay_up=NOW + 200, amt_up=10))
        recent = _scan(
            _row("SIDO", ex_rec=NOW - 10, pay_rec=NOW - 5, amt_rec=15),
            _row("BUAH", ex_rec=NOW - 20, pay_rec=NOW + 10, amt_rec=10),
        )

        def handler(request: httpx.Request) -> httpx.Response:
            field = json.loads(request.content)["filter"][0]["left"]
            data = upcoming if field == "dividend_ex_date_upcoming" else recent
            return httpx.Response(200, json=data)

        respx.post(SCAN_URL).mock(side_effect=handler)

        async with httpx.AsyncClient() as client:
            rows = await fetch_calendar(client, "IDX", NOW)

        by_symbol = {r.symbol: r for r in rows}
        assert len(rows) == 2
        assert by_symbol["SIDO"].kind is CalendarKind.UPCOMING
        assert by_symbol["BUAH"].kind is CalendarKind.PAYING

    async def test_unknown_exchange_makes_no_request(self):
        async with httpx.AsyncClient() as client:
            assert await fetch_calendar(client, "WAT", NOW) == []

    @respx.mock
    async def test_http_error_raises_upstream_error(self):
        respx.post(SCAN_URL).mock(return_value=httpx.Response(500))

        async with httpx.AsyncClient() as client:
            with pytest.raises(UpstreamError, match="500"):
                await fetch_calendar(client, "IDX", NOW)

    @respx.mock
    async def test_non_json_body_raises_parse_error(self):
        respx.post(SCAN_URL).mock(return_value=httpx.Response(200, content=b"<html>"))

        async with httpx.AsyncClient() as client:
            with pytest.raises(ParseError):
                await fetch_calendar(client, "IDX", NOW)


class TestDerivedDates:
    def test_cum_date_is_the_trading_day_before_the_ex_date(self):
        friday_ex = int(datetime(2026, 10, 23, 11, 59, tzinfo=UTC).timestamp())
        entry = CalendarEntry("IDX", "CSRA", None, friday_ex, None, 15.0, 2.0, CalendarKind.PAYING)

        dated = _with_derived_dates(entry)

        assert dated.cum_date == shift_trading_days(friday_ex, -1)
        assert datetime.fromtimestamp(dated.cum_date, UTC).day == 22

    def test_recording_date_is_the_trading_day_after_the_ex_date(self):
        friday_ex = int(datetime(2026, 10, 23, 11, 59, tzinfo=UTC).timestamp())
        entry = CalendarEntry("IDX", "CSRA", None, friday_ex, None, 15.0, 2.0, CalendarKind.PAYING)

        dated = _with_derived_dates(entry)

        assert datetime.fromtimestamp(dated.record_date, UTC).day == 26

    def test_entry_without_an_ex_date_gets_no_derived_dates(self):
        entry = CalendarEntry("IDX", "XXX", None, None, None, None, None, CalendarKind.RECENT)

        assert _with_derived_dates(entry).cum_date is None


class TestRecordLookup:
    def test_record_date_is_taken_from_the_row_with_the_same_ex_date(self):
        raw = {
            "dividend_ex_date_h": [1793707140, 1776686340],
            "dividend_record_date_h": [1793793540, 1776772740],
            "dividend_amount_h": [10, 15],
        }

        assert _record_for(raw, 1776686340) == 1776772740

    def test_no_matching_ex_date_gives_none(self):
        raw = {
            "dividend_ex_date_h": [1793707140],
            "dividend_record_date_h": [1793793540],
        }

        assert _record_for(raw, 1700000000) is None

    async def test_real_record_date_replaces_the_derived_one(self, monkeypatch):
        async def feed(exchange, symbol, max_seconds, fields):
            return {
                "dividend_ex_date_h": [NOW],
                "dividend_record_date_h": [NOW + 86400 * 2],
            }

        monkeypatch.setattr(dividend_calendar, "fetch_quote", feed)
        entry = _with_derived_dates(
            CalendarEntry("IDX", "SIDO", None, NOW, None, 10.0, 10.8, CalendarKind.UPCOMING)
        )

        result = await dividend_calendar._with_record_dates([entry])

        assert result[0].record_date == NOW + 86400 * 2
        assert result[0].record_real

    async def test_failed_lookup_keeps_the_derived_record_date(self):
        entry = _with_derived_dates(
            CalendarEntry("IDX", "SIDO", None, NOW, None, 10.0, 10.8, CalendarKind.UPCOMING)
        )

        result = await dividend_calendar._with_record_dates([entry])

        assert result[0].record_date == entry.record_date
        assert not result[0].record_real

    async def test_lookups_never_exceed_the_concurrency_limit(self, monkeypatch):
        running = 0
        peak = 0

        async def slow(exchange, symbol, max_seconds, fields):
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1
            raise UpstreamError("offline")

        monkeypatch.setattr(dividend_calendar, "fetch_quote", slow)
        entries = [
            _with_derived_dates(
                CalendarEntry("IDX", f"S{i}", None, NOW, None, 1.0, 1.0, CalendarKind.UPCOMING)
            )
            for i in range(12)
        ]

        await dividend_calendar._with_record_dates(entries)

        assert peak <= dividend_calendar.RECORD_LOOKUPS


class TestFundamentalColumns:
    def _row(self, **cols):
        values = [
            "SIDO",
            "PT Sido",
            NOW + 100,
            NOW + 200,
            10.0,
            None,
            None,
            None,
            10.8,
            316.0,
            -6.5,
            26_500_000.0,
            "Health Tech",
            76.4,
            89.5,
            13,
            0,
            1.11,
            7.4,
        ]
        for index, value in cols.items():
            values[int(index[1:])] = value
        return {"s": "IDX:SIDO", "d": values}

    def test_price_volume_sector_payout_and_streak_are_read(self):
        (entry,) = parse_scan(_scan(self._row()), "IDX", NOW)

        assert entry.price == 316.0
        assert entry.avg_volume == 26_500_000.0
        assert entry.sector == "Health Tech"
        assert entry.payout == pytest.approx(76.4)
        assert entry.streak_years == 13
        assert entry.coverage == pytest.approx(1.11)

    def test_a_zero_current_yield_falls_back_to_the_plain_yield(self):
        (entry,) = parse_scan(_scan(self._row(c8=0, c18=7.4)), "IDX", NOW)

        assert entry.yield_pct == pytest.approx(7.4)

    def test_a_zero_ttm_payout_falls_back_to_the_fiscal_year_figure(self):
        (entry,) = parse_scan(_scan(self._row(c13=0, c14=99.4)), "IDX", NOW)

        assert entry.payout == pytest.approx(99.4)

    def test_both_payouts_zero_means_no_payout_data(self):
        (entry,) = parse_scan(_scan(self._row(c13=0, c14=0)), "IDX", NOW)

        assert entry.payout is None

    def test_a_short_row_still_parses_without_fundamentals(self):
        row = _row("OLD", ex_up=NOW + 100, pay_up=NOW + 200, amt_up=10)

        (entry,) = parse_scan(_scan(row), "IDX", NOW)

        assert entry.price is None
        assert entry.payout is None

    def test_event_yield_follows_from_amount_and_price(self):
        (entry,) = parse_scan(_scan(self._row()), "IDX", NOW)

        assert entry.event_yield == pytest.approx(10 / 316 * 100)
