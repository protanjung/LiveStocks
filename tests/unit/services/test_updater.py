import asyncio

import pytest

from livestocks.config import Settings
from livestocks.crawler import CrawlResult, NotFoundError, UpstreamError
from livestocks.domain import ErrorKind, PriceBar, TickerStatus
from livestocks.services import Updater


@pytest.fixture
def settings():
    return Settings(jitter_max=0, refresh_interval=3600, max_failures=3, concurrency=4)


class TestSweep:
    async def test_successful_crawl_stores_forecast_prices_and_extras(
        self, store, settings, make_forecast, quote_data
    ):
        from livestocks.crawler.quote_stream import parse_quote

        await store.add_ticker("IDX", "TLKM")

        async def crawler(exchange, symbol):
            return CrawlResult(make_forecast(symbol), (PriceBar(1, 10.0),), parse_quote(quote_data))

        updater = Updater(store, settings, crawler)
        await updater.sweep()
        await updater.drain()

        [row] = await store.rows()
        assert row.status is TickerStatus.OK
        assert await store.prices("IDX", "TLKM") == [PriceBar(1, 10.0)]
        assert (await store.extras("IDX", "TLKM"))[1].strong_buy == 18

    async def test_crawl_error_is_recorded_with_its_kind_and_backs_off(
        self, store, settings, make_forecast
    ):
        await store.add_ticker("IDX", "TLKM")
        await store.add_ticker("IDX", "ZZZZ")

        async def crawler(exchange, symbol):
            if symbol == "ZZZZ":
                raise NotFoundError("not found on TradingView")
            return CrawlResult(make_forecast(symbol))

        updater = Updater(store, settings, crawler)
        await updater.sweep()
        await updater.drain()
        await updater.sweep()  # nothing is due now: TLKM is fresh and ZZZZ is backing off
        await updater.drain()

        by_symbol = {r.symbol: r for r in await store.rows()}
        assert by_symbol["TLKM"].status is TickerStatus.OK
        assert by_symbol["ZZZZ"].status is TickerStatus.ERROR
        assert by_symbol["ZZZZ"].fail_count == 1
        assert by_symbol["ZZZZ"].error_kind is ErrorKind.NOT_FOUND
        assert updater.fetching == set()

    async def test_unexpected_exception_is_recorded_without_stopping_other_tickers(
        self, store, settings, make_forecast
    ):
        await store.add_ticker("IDX", "BAD")
        await store.add_ticker("IDX", "TLKM")

        async def crawler(exchange, symbol):
            if symbol == "BAD":
                raise RuntimeError("bug")
            return CrawlResult(make_forecast(symbol))

        updater = Updater(store, settings, crawler)
        await updater.sweep()
        await updater.drain()

        by_symbol = {r.symbol: r for r in await store.rows()}
        assert by_symbol["TLKM"].status is TickerStatus.OK
        assert by_symbol["BAD"].last_error == "unexpected: RuntimeError"
        assert by_symbol["BAD"].error_kind is ErrorKind.UPSTREAM

    async def test_overlapping_sweeps_do_not_crawl_a_ticker_twice(
        self, store, settings, make_forecast
    ):
        await store.add_ticker("IDX", "TLKM")
        release = asyncio.Event()
        calls: list[str] = []

        async def crawler(exchange, symbol):
            calls.append(symbol)
            await release.wait()
            return CrawlResult(make_forecast(symbol))

        updater = Updater(store, settings, crawler)
        await updater.sweep()
        await asyncio.sleep(0)
        await updater.sweep()  # the first crawl is still running
        release.set()
        await updater.drain()

        assert calls == ["TLKM"]

    async def test_a_new_ticker_starts_while_another_crawl_is_still_running(
        self, store, settings, make_forecast
    ):
        await store.add_ticker("IDX", "SLOW")
        release = asyncio.Event()
        started: list[str] = []

        async def crawler(exchange, symbol):
            started.append(symbol)
            if symbol == "SLOW":
                await release.wait()
            return CrawlResult(make_forecast(symbol))

        updater = Updater(store, settings, crawler)
        await updater.sweep()
        await asyncio.sleep(0)
        await store.add_ticker("IDX", "FAST")
        await updater.sweep()
        await asyncio.sleep(0.01)

        assert started == ["SLOW", "FAST"]
        assert {r.symbol: r.status for r in await store.rows()}["FAST"] is TickerStatus.OK
        release.set()
        await updater.drain()

    async def test_a_ticker_removed_during_its_crawl_leaves_nothing_behind(
        self, store, settings, make_forecast
    ):
        await store.add_ticker("IDX", "TLKM")
        release = asyncio.Event()

        async def crawler(exchange, symbol):
            await release.wait()
            return CrawlResult(make_forecast(symbol))

        updater = Updater(store, settings, crawler)
        await updater.sweep()
        await asyncio.sleep(0)
        await store.remove_ticker("IDX", "TLKM")
        release.set()
        await updater.drain()

        assert await store.rows() == []
        assert await store.history("IDX", "TLKM") == []


class TestWatch:
    async def test_watcher_resolves_when_the_crawl_succeeds(self, store, settings, make_forecast):
        await store.add_ticker("IDX", "TLKM")

        async def crawler(exchange, symbol):
            return CrawlResult(make_forecast(symbol))

        updater = Updater(store, settings, crawler)
        waiter = updater.watch("IDX:TLKM")
        await updater.sweep()
        await updater.drain()

        assert waiter.done()
        assert waiter.result() is None

    async def test_watcher_receives_the_crawl_error(self, store, settings):
        await store.add_ticker("IDX", "ZZZZ")

        async def crawler(exchange, symbol):
            raise NotFoundError("not found on TradingView")

        updater = Updater(store, settings, crawler)
        waiter = updater.watch("IDX:ZZZZ")
        await updater.sweep()
        await updater.drain()

        with pytest.raises(NotFoundError):
            waiter.result()

    async def test_unwatched_futures_are_not_resolved(self, store, settings, make_forecast):
        await store.add_ticker("IDX", "TLKM")

        async def crawler(exchange, symbol):
            return CrawlResult(make_forecast(symbol))

        updater = Updater(store, settings, crawler)
        waiter = updater.watch("IDX:TLKM")
        updater.unwatch("IDX:TLKM", waiter)
        await updater.sweep()
        await updater.drain()

        assert not waiter.done()

    async def test_stop_tells_watchers_the_updater_stopped(self, store, settings):
        updater = Updater(store, settings, crawler=None)
        waiter = updater.watch("IDX:TLKM")

        await updater.stop()

        with pytest.raises(UpstreamError, match="stopped"):
            waiter.result()
