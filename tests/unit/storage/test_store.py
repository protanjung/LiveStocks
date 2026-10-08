import pytest

from livestocks.domain import PriceBar, TickerStatus
from livestocks.storage import Store


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


class TestTrackedTickers:
    def test_add_ignores_duplicates_and_starts_pending(self, store):
        assert store.add_ticker("IDX", "TLKM") is True
        assert store.add_ticker("IDX", "TLKM") is False

        [row] = store.rows()
        assert row.status is TickerStatus.PENDING
        assert row.forecast is None
        assert store.due() == [("IDX", "TLKM")]

    def test_remove_deletes_snapshots_prices_and_extras(self, store, make_forecast):
        store.add_ticker("IDX", "TLKM")
        store.record_success(make_forecast(), 3600, now=1)
        store.upsert_prices("IDX", "TLKM", [PriceBar(1, 10.0)])

        store.remove_ticker("IDX", "TLKM")

        assert store.rows() == []
        assert store.history("IDX", "TLKM") == []
        assert store.prices("IDX", "TLKM") == []


class TestCrawlOutcomes:
    def test_success_keeps_history_and_exposes_the_latest_snapshot(self, store, make_forecast):
        store.add_ticker("IDX", "TLKM")
        store.record_success(make_forecast(price=2000.0), 3600, now=1000)
        store.record_success(make_forecast(price=2310.0), 3600, now=2000)

        [row] = store.rows()
        assert row.status is TickerStatus.OK
        assert row.forecast.price == 2310.0
        assert row.name == "Telkom"
        assert row.upside == pytest.approx(3394 / 2310 - 1)
        assert [t for t, _ in store.history("IDX", "TLKM")] == [1000, 2000]

    def test_ticker_is_due_again_after_the_refresh_interval(self, store, make_forecast):
        store.add_ticker("IDX", "TLKM")
        store.record_success(make_forecast(), 3600, now=2000)

        assert store.due(now=2000) == []
        assert store.due(now=2000 + 3600) == [("IDX", "TLKM")]

    def test_repeated_failures_back_off_then_mark_the_ticker_dead(self, store):
        store.add_ticker("IDX", "ZZZZ")
        for _ in range(3):
            store.record_failure("IDX", "ZZZZ", "not found", 3600, 3, now=100)

        [row] = store.rows()
        assert row.dead
        assert row.status is TickerStatus.FAILED
        assert row.last_error == "not found"
        assert store.due(now=10**9) == []

    def test_retry_clears_failure_state(self, store):
        store.add_ticker("IDX", "ZZZZ")
        for _ in range(3):
            store.record_failure("IDX", "ZZZZ", "not found", 3600, 3, now=100)

        store.retry("IDX", "ZZZZ")

        assert store.due(now=1) == [("IDX", "ZZZZ")]
        assert not store.rows()[0].dead


class TestPrices:
    def test_upsert_replaces_bars_with_the_same_timestamp(self, store):
        store.add_ticker("IDX", "TLKM")
        store.upsert_prices("IDX", "TLKM", [PriceBar(1, 10.0), PriceBar(2, 11.0)])
        store.upsert_prices("IDX", "TLKM", [PriceBar(2, 12.0), PriceBar(3, 13.0)])

        assert store.prices("IDX", "TLKM") == [
            PriceBar(1, 10.0),
            PriceBar(2, 12.0),
            PriceBar(3, 13.0),
        ]
        assert store.prices("IDX", "TLKM", since=2) == [PriceBar(2, 12.0), PriceBar(3, 13.0)]


class TestExtras:
    def test_round_trips_through_json(self, store, quote_data):
        from livestocks.crawler.quote_stream import parse_quote

        store.add_ticker("IDX", "TLKM")
        extras = parse_quote(quote_data)

        store.save_extras("IDX", "TLKM", extras, now=5)

        assert store.extras("IDX", "TLKM") == (5, extras)

    def test_remove_ticker_drops_extras(self, store, quote_data):
        from livestocks.crawler.quote_stream import parse_quote

        store.add_ticker("IDX", "TLKM")
        store.save_extras("IDX", "TLKM", parse_quote(quote_data))

        store.remove_ticker("IDX", "TLKM")

        assert store.extras("IDX", "TLKM") is None

    def test_queue_missing_extras_requeues_only_tickers_without_them(self, store, quote_data):
        from livestocks.crawler.quote_stream import parse_quote

        store.add_ticker("IDX", "A")
        store.add_ticker("IDX", "B")
        store._db.execute("UPDATE tickers SET last_fetch = 100, next_fetch = 99999")
        store.save_extras("IDX", "A", parse_quote(quote_data))

        store.queue_missing_extras()

        assert store.due(now=1) == [("IDX", "B")]
