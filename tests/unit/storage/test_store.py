import pytest

from livestocks.domain import PriceBar, TickerStatus


class TestTrackedTickers:
    async def test_add_ignores_duplicates_and_starts_pending(self, store):
        assert await store.add_ticker("IDX", "TLKM") is True
        assert await store.add_ticker("IDX", "TLKM") is False

        [row] = await store.rows()
        assert row.status is TickerStatus.PENDING
        assert row.forecast is None
        assert await store.due() == [("IDX", "TLKM")]

    async def test_remove_deletes_snapshots_prices_and_extras(self, store, make_forecast):
        await store.add_ticker("IDX", "TLKM")
        await store.record_success(make_forecast(), 3600, now=1)
        await store.upsert_prices("IDX", "TLKM", [PriceBar(1, 10.0)])

        await store.remove_ticker("IDX", "TLKM")

        assert await store.rows() == []
        assert await store.history("IDX", "TLKM") == []
        assert await store.prices("IDX", "TLKM") == []


class TestCrawlOutcomes:
    async def test_success_keeps_history_and_exposes_the_latest_snapshot(
        self, store, make_forecast
    ):
        await store.add_ticker("IDX", "TLKM")
        await store.record_success(make_forecast(price=2000.0), 3600, now=1000)
        await store.record_success(make_forecast(price=2310.0), 3600, now=2000)

        [row] = await store.rows()
        assert row.status is TickerStatus.OK
        assert row.forecast.price == 2310.0
        assert row.name == "Telkom"
        assert row.upside == pytest.approx(3394 / 2310 - 1)
        assert [t for t, _ in await store.history("IDX", "TLKM")] == [1000, 2000]

    async def test_ticker_is_due_again_after_the_refresh_interval(self, store, make_forecast):
        await store.add_ticker("IDX", "TLKM")
        await store.record_success(make_forecast(), 3600, now=2000)

        assert await store.due(now=2000) == []
        assert await store.due(now=2000 + 3600) == [("IDX", "TLKM")]

    async def test_repeated_failures_back_off_then_mark_the_ticker_dead(self, store):
        await store.add_ticker("IDX", "ZZZZ")
        for _ in range(3):
            await store.record_failure("IDX", "ZZZZ", "not found", 3600, 3, now=100)

        [row] = await store.rows()
        assert row.dead
        assert row.status is TickerStatus.FAILED
        assert row.last_error == "not found"
        assert await store.due(now=10**9) == []

    async def test_retry_clears_failure_state(self, store):
        await store.add_ticker("IDX", "ZZZZ")
        for _ in range(3):
            await store.record_failure("IDX", "ZZZZ", "not found", 3600, 3, now=100)

        await store.retry("IDX", "ZZZZ")

        assert await store.due(now=1) == [("IDX", "ZZZZ")]
        assert not (await store.rows())[0].dead


class TestPrices:
    async def test_upsert_replaces_bars_with_the_same_timestamp(self, store):
        await store.add_ticker("IDX", "TLKM")
        await store.upsert_prices("IDX", "TLKM", [PriceBar(1, 10.0), PriceBar(2, 11.0)])
        await store.upsert_prices("IDX", "TLKM", [PriceBar(2, 12.0), PriceBar(3, 13.0)])

        assert await store.prices("IDX", "TLKM") == [
            PriceBar(1, 10.0),
            PriceBar(2, 12.0),
            PriceBar(3, 13.0),
        ]
        assert await store.prices("IDX", "TLKM", since=2) == [PriceBar(2, 12.0), PriceBar(3, 13.0)]


class TestExtras:
    async def test_round_trips_through_json(self, store, quote_data):
        from livestocks.crawler.quote_stream import parse_quote

        await store.add_ticker("IDX", "TLKM")
        extras = parse_quote(quote_data)

        await store.save_extras("IDX", "TLKM", extras, now=5)

        assert await store.extras("IDX", "TLKM") == (5, extras)

    async def test_remove_ticker_drops_extras(self, store, quote_data):
        from livestocks.crawler.quote_stream import parse_quote

        await store.add_ticker("IDX", "TLKM")
        await store.save_extras("IDX", "TLKM", parse_quote(quote_data))

        await store.remove_ticker("IDX", "TLKM")

        assert await store.extras("IDX", "TLKM") is None

    async def test_queue_missing_extras_requeues_only_tickers_without_them(
        self, store, quote_data, make_forecast
    ):
        from livestocks.crawler.quote_stream import parse_quote

        await store.add_ticker("IDX", "A")
        await store.add_ticker("IDX", "B")
        for symbol in ("A", "B"):
            await store.record_success(make_forecast(symbol), 99999, now=100)
        await store.save_extras("IDX", "A", parse_quote(quote_data))

        await store.queue_missing_extras()

        assert await store.due(now=1) == [("IDX", "B")]


class TestErrorKind:
    async def test_failure_records_why_and_success_clears_it(self, store, make_forecast):
        from livestocks.domain import ErrorKind

        await store.add_ticker("IDX", "TLKM")
        await store.record_failure("IDX", "TLKM", "HTTP 503", 3600, 5, kind=ErrorKind.UPSTREAM)
        assert (await store.row("IDX", "TLKM")).error_kind is ErrorKind.UPSTREAM

        await store.record_success(make_forecast(), 3600)

        assert (await store.row("IDX", "TLKM")).error_kind is None

    async def test_retry_clears_the_kind(self, store):
        from livestocks.domain import ErrorKind

        await store.add_ticker("IDX", "ZZZZ")
        await store.record_failure("IDX", "ZZZZ", "gone", 3600, 5, kind=ErrorKind.NOT_FOUND)

        await store.retry("IDX", "ZZZZ")

        assert (await store.row("IDX", "ZZZZ")).error_kind is None


class TestRemovedWhileCrawling:
    async def test_a_success_for_an_untracked_ticker_is_ignored(self, store, make_forecast):
        await store.record_success(make_forecast(), 3600)

        assert await store.history("IDX", "TLKM") == []
