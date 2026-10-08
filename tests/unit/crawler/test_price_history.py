import httpx
import pytest
import respx

from livestocks.crawler import ParseError, UpstreamError
from livestocks.crawler.price_history import fetch_prices, parse_chart, yahoo_symbol
from livestocks.domain import PriceBar


class TestYahooSymbol:
    @pytest.mark.parametrize(
        ("exchange", "symbol", "expected"),
        [
            ("IDX", "TLKM", "TLKM.JK"),
            ("NASDAQ", "AAPL", "AAPL"),
            ("NYSE", "BRK.B", "BRK-B"),
            ("WAT", "X", None),
        ],
    )
    def test_maps_exchange_to_yahoo_suffix(self, exchange, symbol, expected):
        assert yahoo_symbol(exchange, symbol) == expected


class TestParseChart:
    def test_skips_bars_with_null_close(self):
        data = {
            "chart": {
                "result": [
                    {"timestamp": [1, 2, 3], "indicators": {"quote": [{"close": [1.5, None, 2.5]}]}}
                ]
            }
        }

        assert parse_chart(data) == [PriceBar(1, 1.5), PriceBar(3, 2.5)]

    def test_unexpected_shape_raises_parse_error(self):
        with pytest.raises(ParseError):
            parse_chart({"chart": {"result": None}})


class TestFetchPrices:
    async def test_unsupported_exchange_returns_no_bars(self):
        async with httpx.AsyncClient() as client:
            assert await fetch_prices(client, "WAT", "X") == []

    @respx.mock
    async def test_http_error_raises_upstream_error(self):
        respx.get(url__regex=r".*finance/chart.*").mock(return_value=httpx.Response(500))

        async with httpx.AsyncClient() as client:
            with pytest.raises(UpstreamError, match="500"):
                await fetch_prices(client, "IDX", "TLKM")
