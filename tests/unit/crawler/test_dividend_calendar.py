import json

import httpx
import pytest
import respx

from livestocks.crawler import ParseError, UpstreamError
from livestocks.crawler.dividend_calendar import fetch_calendar, parse_scan, scanner_market
from livestocks.domain import CalendarKind

NOW = 1_790_000_000
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
