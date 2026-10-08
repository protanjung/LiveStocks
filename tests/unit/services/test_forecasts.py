import asyncio

import pytest

from livestocks.config import Settings
from livestocks.crawler import CrawlResult, NotFoundError, UpstreamError
from livestocks.domain import ErrorKind, InvalidTickerError, PriceBar, TickerId, TickerStatus
from livestocks.services import (
    CrawlTimeoutError,
    ForecastService,
    TickerNotFoundError,
    Updater,
    UpstreamUnavailableError,
)

TLKM = TickerId("IDX", "TLKM")


@pytest.fixture
def service(store):
    settings = Settings(jitter_max=0, refresh_interval=3600)

    async def crawler(exchange, symbol):
        raise AssertionError("the crawler must not run in these tests")

    return ForecastService(store, Updater(store, settings, crawler), settings)


class TestTrack:
    async def test_new_ticker_is_stored_pending_and_reported_as_created(self, service):
        result = await service.track("tlkm")

        assert result.ticker == TLKM
        assert result.created is True
        assert [t.status for t in await service.list_tickers()] == [TickerStatus.PENDING]

    async def test_default_exchange_applies_to_bare_symbols_only(self, service):
        await service.track("nasdaq:aapl")
        await service.track("bbca")

        assert {t.key for t in await service.list_tickers()} == {"NASDAQ:AAPL", "IDX:BBCA"}

    async def test_tracking_an_existing_ticker_retries_it_instead(self, service, store):
        await service.track("tlkm")
        for _ in range(5):
            await store.record_failure("IDX", "TLKM", "boom", 3600, 5)
        assert (await service.list_tickers())[0].status is TickerStatus.FAILED

        result = await service.track("tlkm")

        assert result.created is False
        assert (await service.list_tickers())[0].status is TickerStatus.PENDING

    async def test_malformed_text_raises_invalid_ticker_error(self, service):
        with pytest.raises(InvalidTickerError):
            await service.track("a b")
        assert await service.list_tickers() == []


class TestRead:
    async def test_get_ticker_is_none_when_not_tracked(self, service):
        assert await service.get_ticker(TLKM) is None

    async def test_get_ticker_bundles_extras_and_a_signature(self, service, store, quote_data):
        from livestocks.crawler.quote_stream import parse_quote

        await service.track("tlkm")
        await store.save_extras("IDX", "TLKM", parse_quote(quote_data), now=7)

        view = await service.get_ticker(TLKM)

        assert view is not None
        assert view.extras is not None
        assert view.extras.strong_buy == 18
        assert view.extras_fetched_at == 7
        assert view.signature == (None, "pending", None, 7)

    async def test_price_history_prefers_crawled_bars(self, service, store):
        await service.track("tlkm")
        await store.upsert_prices("IDX", "TLKM", [PriceBar(1, 10.0), PriceBar(2, 11.0)])

        assert await service.price_history(TLKM) == [PriceBar(1, 10.0), PriceBar(2, 11.0)]

    async def test_price_history_falls_back_to_forecast_snapshots(
        self, service, store, make_forecast
    ):
        await service.track("tlkm")
        await store.record_success(make_forecast(price=2000.0), 3600, now=100)
        await store.record_success(make_forecast(price=2100.0), 3600, now=200)

        assert await service.price_history(TLKM) == [PriceBar(100, 2000.0), PriceBar(200, 2100.0)]

    async def test_price_history_respects_the_since_bound(self, service, store):
        await service.track("tlkm")
        await store.upsert_prices(
            "IDX", "TLKM", [PriceBar(1, 10.0), PriceBar(2, 11.0), PriceBar(3, 12.0)]
        )

        assert await service.price_history(TLKM, since=2) == [PriceBar(2, 11.0), PriceBar(3, 12.0)]

    async def test_next_refresh_is_none_without_tickers_and_zero_when_one_is_due(self, service):
        assert await service.seconds_until_next_refresh() is None

        await service.track("tlkm")

        assert await service.seconds_until_next_refresh() == 0

    async def test_fetching_is_an_immutable_snapshot(self, service):
        assert service.fetching() == frozenset()


class TestRemoveAndRetry:
    async def test_remove_forgets_the_ticker(self, service):
        await service.track("tlkm")

        await service.remove(TLKM)

        assert await service.list_tickers() == []

    async def test_retry_revives_a_failed_ticker(self, service, store):
        await service.track("tlkm")
        for _ in range(5):
            await store.record_failure("IDX", "TLKM", "boom", 3600, 5)

        await service.retry(TLKM)

        assert (await service.list_tickers())[0].status is TickerStatus.PENDING


class TestWakeUp:
    async def test_tracking_wakes_the_updater(self, store, make_forecast):
        settings = Settings(jitter_max=0, refresh_interval=3600)
        crawled: list[str] = []

        async def crawler(exchange, symbol):
            crawled.append(symbol)
            return CrawlResult(make_forecast(symbol))

        updater = Updater(store, settings, crawler)
        service = ForecastService(store, updater, settings)
        await service.track("tlkm")

        await updater.sweep()
        await updater.drain()

        assert crawled == ["TLKM"]
        assert (await service.list_tickers())[0].status is TickerStatus.OK


@pytest.fixture
async def running(store):
    """A service whose updater loop is running; crawl behaviour is set through ``plan``."""
    settings = Settings(jitter_max=0, refresh_interval=3600, poll_interval=60, api_wait_seconds=2)
    plan: dict = {"calls": [], "delay": None, "error": None, "forecast": None}

    async def crawler(exchange, symbol):
        plan["calls"].append(symbol)
        if plan["delay"] is not None:
            await plan["delay"].wait()
        if plan["error"] is not None:
            raise plan["error"]
        return CrawlResult(plan["forecast"](symbol))

    updater = Updater(store, settings, crawler)
    await updater.start()
    yield ForecastService(store, updater, settings), plan
    await updater.stop()


class TestGetOrTrack:
    async def test_unknown_ticker_is_tracked_and_returned_after_its_first_crawl(
        self, running, make_forecast
    ):
        service, plan = running
        plan["forecast"] = make_forecast

        result = await service.get_or_track("tlkm")

        assert result.created is True
        assert result.stale is False
        assert result.view.ticker.forecast.pt_high == 4150
        assert plan["calls"] == ["TLKM"]

    async def test_known_ticker_is_answered_from_storage_without_crawling(
        self, running, store, make_forecast
    ):
        service, plan = running
        await store.add_ticker("IDX", "TLKM")
        await store.record_success(make_forecast(), 3600)

        result = await service.get_or_track("tlkm")

        assert result.created is False
        assert plan["calls"] == []

    async def test_data_older_than_two_refresh_intervals_is_marked_stale(
        self, running, store, make_forecast
    ):
        service, _ = running
        await store.add_ticker("IDX", "TLKM")
        await store.record_success(make_forecast(), 3600, now=1)

        result = await service.get_or_track("tlkm")

        assert result.stale is True

    async def test_malformed_ticker_raises_before_anything_is_tracked(self, running):
        service, _ = running

        with pytest.raises(InvalidTickerError):
            await service.get_or_track("a b")

        assert await service.list_tickers() == []

    async def test_unknown_to_tradingview_raises_ticker_not_found(self, running):
        service, plan = running
        plan["error"] = NotFoundError("not found on TradingView")

        with pytest.raises(TickerNotFoundError, match="not found"):
            await service.get_or_track("zzzz")

    async def test_upstream_failure_raises_upstream_unavailable(self, running):
        service, plan = running
        plan["error"] = UpstreamError("HTTP 503")

        with pytest.raises(UpstreamUnavailableError, match="503"):
            await service.get_or_track("tlkm")

    async def test_a_ticker_already_failing_fails_fast_by_error_kind(self, running, store):
        service, plan = running
        await store.add_ticker("IDX", "ZZZZ")
        await store.record_failure(
            "IDX", "ZZZZ", "not found on TradingView", 3600, 5, kind=ErrorKind.NOT_FOUND
        )

        with pytest.raises(TickerNotFoundError):
            await service.get_or_track("zzzz")

        assert plan["calls"] == []

    async def test_slow_first_crawl_times_out_and_keeps_running(self, running, make_forecast):
        service, plan = running
        plan["delay"] = asyncio.Event()
        plan["forecast"] = make_forecast

        with pytest.raises(CrawlTimeoutError):
            await service.get_or_track("tlkm", wait_seconds=0.05)

        plan["delay"].set()
        result = await service.get_or_track("tlkm", wait_seconds=1)
        assert result.view.ticker.forecast is not None
        assert plan["calls"] == ["TLKM"]

    async def test_concurrent_first_requests_share_one_crawl(self, running, make_forecast):
        service, plan = running
        plan["forecast"] = make_forecast
        plan["delay"] = asyncio.Event()

        pending = [asyncio.create_task(service.get_or_track("tlkm")) for _ in range(3)]
        await asyncio.sleep(0.05)
        plan["delay"].set()
        results = await asyncio.gather(*pending)

        assert plan["calls"] == ["TLKM"]
        assert all(r.view.ticker.forecast is not None for r in results)
