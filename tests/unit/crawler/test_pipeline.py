import httpx
import pytest

from livestocks.crawler import NotFoundError, UpstreamError, crawl_ticker
from livestocks.domain import PriceBar


@pytest.fixture
def stub_fetchers(monkeypatch, make_forecast, quote_data):
    from livestocks.crawler.quote_stream import parse_quote

    state = {"forecast": make_forecast(), "prices": [PriceBar(1, 10.0)], "extras": parse_quote(quote_data)}

    async def forecast(client, exchange, symbol):
        value = state["forecast"]
        if isinstance(value, Exception):
            raise value
        return value

    async def prices(client, exchange, symbol):
        value = state["prices"]
        if isinstance(value, Exception):
            raise value
        return value

    async def extras(exchange, symbol):
        value = state["extras"]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr("livestocks.crawler.pipeline.fetch_forecast", forecast)
    monkeypatch.setattr("livestocks.crawler.pipeline.fetch_prices", prices)
    monkeypatch.setattr("livestocks.crawler.pipeline.fetch_extras", extras)
    return state


class TestCrawlTicker:
    async def test_collects_forecast_prices_and_extras(self, stub_fetchers):
        async with httpx.AsyncClient() as client:
            result = await crawl_ticker(client, "IDX", "TLKM")

        assert result.forecast.symbol == "TLKM"
        assert result.prices == (PriceBar(1, 10.0),)
        assert result.extras is not None and result.extras.strong_buy == 18
        assert result.prices_error is None and result.extras_error is None

    async def test_optional_failures_keep_the_forecast(self, stub_fetchers):
        stub_fetchers["prices"] = UpstreamError("price history HTTP 500")
        stub_fetchers["extras"] = RuntimeError("socket closed")

        async with httpx.AsyncClient() as client:
            result = await crawl_ticker(client, "IDX", "TLKM")

        assert result.forecast.symbol == "TLKM"
        assert result.prices is None and result.prices_error == "price history HTTP 500"
        assert result.extras is None and result.extras_error == "socket closed"

    async def test_forecast_failure_propagates(self, stub_fetchers):
        stub_fetchers["forecast"] = NotFoundError("not found on TradingView")

        async with httpx.AsyncClient() as client:
            with pytest.raises(NotFoundError):
                await crawl_ticker(client, "IDX", "ZZZZ")
