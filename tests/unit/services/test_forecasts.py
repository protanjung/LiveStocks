import pytest

from livestocks.config import Settings
from livestocks.crawler import CrawlResult
from livestocks.domain import InvalidTickerError, PriceBar, TickerId, TickerStatus
from livestocks.services import ForecastService, Updater
from livestocks.storage import Store

TLKM = TickerId("IDX", "TLKM")


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def service(store):
    settings = Settings(jitter_max=0, refresh_interval=3600)

    async def crawler(exchange, symbol):
        raise AssertionError("the crawler must not run in these tests")

    return ForecastService(store, Updater(store, settings, crawler), settings)


class TestTrack:
    def test_new_ticker_is_stored_pending_and_reported_as_created(self, service):
        result = service.track("tlkm")

        assert result.ticker == TLKM
        assert result.created is True
        assert [t.status for t in service.list_tickers()] == [TickerStatus.PENDING]

    def test_default_exchange_applies_to_bare_symbols_only(self, service):
        service.track("nasdaq:aapl")
        service.track("bbca")

        assert {t.key for t in service.list_tickers()} == {"NASDAQ:AAPL", "IDX:BBCA"}

    def test_tracking_an_existing_ticker_retries_it_instead(self, service, store):
        service.track("tlkm")
        for _ in range(5):
            store.record_failure("IDX", "TLKM", "boom", 3600, 5)
        assert service.list_tickers()[0].status is TickerStatus.FAILED

        result = service.track("tlkm")

        assert result.created is False
        assert service.list_tickers()[0].status is TickerStatus.PENDING

    def test_malformed_text_raises_invalid_ticker_error(self, service):
        with pytest.raises(InvalidTickerError):
            service.track("a b")
        assert service.list_tickers() == []


class TestRead:
    def test_get_ticker_is_none_when_not_tracked(self, service):
        assert service.get_ticker(TLKM) is None

    def test_get_ticker_bundles_extras_and_a_signature(self, service, store, quote_data):
        from livestocks.crawler.quote_stream import parse_quote

        service.track("tlkm")
        store.save_extras("IDX", "TLKM", parse_quote(quote_data), now=7)

        view = service.get_ticker(TLKM)

        assert view is not None
        assert view.extras is not None
        assert view.extras.strong_buy == 18
        assert view.extras_fetched_at == 7
        assert view.signature == (None, "pending", None, 7)

    def test_price_history_prefers_crawled_bars(self, service, store):
        service.track("tlkm")
        store.upsert_prices("IDX", "TLKM", [PriceBar(1, 10.0), PriceBar(2, 11.0)])

        assert service.price_history(TLKM) == [PriceBar(1, 10.0), PriceBar(2, 11.0)]

    def test_price_history_falls_back_to_forecast_snapshots(self, service, store, make_forecast):
        service.track("tlkm")
        store.record_success(make_forecast(price=2000.0), 3600, now=100)
        store.record_success(make_forecast(price=2100.0), 3600, now=200)

        assert service.price_history(TLKM) == [PriceBar(100, 2000.0), PriceBar(200, 2100.0)]

    def test_price_history_respects_the_since_bound(self, service, store):
        service.track("tlkm")
        store.upsert_prices(
            "IDX", "TLKM", [PriceBar(1, 10.0), PriceBar(2, 11.0), PriceBar(3, 12.0)]
        )

        assert service.price_history(TLKM, since=2) == [PriceBar(2, 11.0), PriceBar(3, 12.0)]

    def test_next_refresh_is_none_without_tickers_and_zero_when_one_is_due(self, service):
        assert service.seconds_until_next_refresh() is None

        service.track("tlkm")

        assert service.seconds_until_next_refresh() == 0

    def test_fetching_is_an_immutable_snapshot(self, service):
        assert service.fetching() == frozenset()


class TestRemoveAndRetry:
    def test_remove_forgets_the_ticker(self, service):
        service.track("tlkm")

        service.remove(TLKM)

        assert service.list_tickers() == []

    def test_retry_revives_a_failed_ticker(self, service, store):
        service.track("tlkm")
        for _ in range(5):
            store.record_failure("IDX", "TLKM", "boom", 3600, 5)

        service.retry(TLKM)

        assert service.list_tickers()[0].status is TickerStatus.PENDING


class TestWakeUp:
    async def test_tracking_wakes_the_updater(self, store, make_forecast):
        settings = Settings(jitter_max=0, refresh_interval=3600)
        crawled: list[str] = []

        async def crawler(exchange, symbol):
            crawled.append(symbol)
            return CrawlResult(make_forecast(symbol))

        updater = Updater(store, settings, crawler)
        service = ForecastService(store, updater, settings)
        service.track("tlkm")

        await updater.sweep()

        assert crawled == ["TLKM"]
        assert service.list_tickers()[0].status is TickerStatus.OK
