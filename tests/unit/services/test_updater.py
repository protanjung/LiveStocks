import pytest

from livestocks.config import Settings
from livestocks.crawler import CrawlResult, NotFoundError
from livestocks.domain import PriceBar, TickerStatus
from livestocks.services import Updater
from livestocks.storage import Store


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def settings():
    return Settings(jitter_max=0, refresh_interval=3600, max_failures=3)


class TestSweep:
    async def test_successful_crawl_stores_forecast_prices_and_extras(
        self, store, settings, make_forecast, quote_data
    ):
        from livestocks.crawler.quote_stream import parse_quote

        store.add_ticker("IDX", "TLKM")

        async def crawler(exchange, symbol):
            return CrawlResult(make_forecast(symbol), (PriceBar(1, 10.0),), parse_quote(quote_data))

        await Updater(store, settings, crawler).sweep()

        [row] = store.rows()
        assert row.status is TickerStatus.OK
        assert store.prices("IDX", "TLKM") == [PriceBar(1, 10.0)]
        assert store.extras("IDX", "TLKM")[1].strong_buy == 18

    async def test_crawl_error_is_recorded_and_backs_off(self, store, settings, make_forecast):
        store.add_ticker("IDX", "TLKM")
        store.add_ticker("IDX", "ZZZZ")

        async def crawler(exchange, symbol):
            if symbol == "ZZZZ":
                raise NotFoundError("not found on TradingView")
            return CrawlResult(make_forecast(symbol))

        updater = Updater(store, settings, crawler)
        await updater.sweep()
        await updater.sweep()  # nothing is due now: TLKM is fresh and ZZZZ is backing off

        by_symbol = {r.symbol: r for r in store.rows()}
        assert by_symbol["TLKM"].status is TickerStatus.OK
        assert by_symbol["ZZZZ"].status is TickerStatus.ERROR and by_symbol["ZZZZ"].fail_count == 1
        assert updater.fetching == set()

    async def test_unexpected_exception_is_recorded_without_stopping_other_tickers(
        self, store, settings, make_forecast
    ):
        store.add_ticker("IDX", "BAD")
        store.add_ticker("IDX", "TLKM")

        async def crawler(exchange, symbol):
            if symbol == "BAD":
                raise RuntimeError("bug")
            return CrawlResult(make_forecast(symbol))

        await Updater(store, settings, crawler).sweep()

        by_symbol = {r.symbol: r for r in store.rows()}
        assert by_symbol["TLKM"].status is TickerStatus.OK
        assert by_symbol["BAD"].last_error == "unexpected: RuntimeError"
