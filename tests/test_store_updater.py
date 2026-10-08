import pytest

from livestocks.config import Settings
from livestocks.models import Forecast
from livestocks.scraper import NotFoundError
from livestocks.store import Store
from livestocks.updater import Updater


def fc(sym="TLKM", **kw):
    base = dict(exchange="IDX", symbol=sym, name="Telkom", price=2310.0, change_pct=1.75, pt_avg=3394.0,
                pt_high=4150.0, pt_low=2300.0, n_analysts=22, rating_mark=1.2, n_ratings=23, ath=4850.0,
                next_earnings=1793275200)
    base.update(kw)
    return Forecast(**base)


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


def settings(**kw):
    return Settings(jitter_max=0, refresh_interval=3600, max_failures=3, **kw)


def test_add_dedup_and_pending(store):
    assert store.add_ticker("IDX", "TLKM") is True
    assert store.add_ticker("IDX", "TLKM") is False
    [row] = store.rows()
    assert row.status == "pending" and row.forecast is None
    assert store.due() == [("IDX", "TLKM")]


def test_success_history_and_latest(store):
    store.add_ticker("IDX", "TLKM")
    store.record_success(fc(price=2000.0), 3600, now=1000)
    store.record_success(fc(price=2310.0), 3600, now=2000)
    [row] = store.rows()
    assert row.status == "ok" and row.forecast.price == 2310.0 and row.name == "Telkom"
    assert row.upside == pytest.approx(3394 / 2310 - 1)
    assert [t for t, _ in store.history("IDX", "TLKM")] == [1000, 2000]
    assert store.due(now=2000) == []
    assert store.due(now=2000 + 3600) == [("IDX", "TLKM")]


def test_failure_backoff_then_dead_and_retry(store):
    store.add_ticker("IDX", "ZZZZ")
    for i in range(3):
        store.record_failure("IDX", "ZZZZ", "not found", 3600, 3, now=100)
    [row] = store.rows()
    assert row.dead and row.status == "failed" and row.last_error == "not found"
    assert store.due(now=10**9) == []
    store.retry("IDX", "ZZZZ")
    assert store.due(now=0) == [("IDX", "ZZZZ")] and not store.rows()[0].dead


def test_remove_deletes_history(store):
    store.add_ticker("IDX", "TLKM")
    store.record_success(fc(), 3600, now=1)
    store.remove_ticker("IDX", "TLKM")
    assert store.rows() == [] and store.history("IDX", "TLKM") == []


async def test_updater_sweep(store):
    store.add_ticker("IDX", "TLKM")
    store.add_ticker("IDX", "ZZZZ")

    async def fetcher(ex, sym):
        if sym == "ZZZZ":
            raise NotFoundError("not found on TradingView")
        return fc(sym)

    u = Updater(store, settings(), fetcher)
    await u.sweep()
    by = {r.symbol: r for r in store.rows()}
    assert by["TLKM"].status == "ok"
    assert by["ZZZZ"].status == "error" and by["ZZZZ"].fail_count == 1
    assert u.fetching == set()
    await u.sweep()  # nothing due now: ZZZZ is backing off, TLKM is fresh
    assert store.rows()[0].fail_count + store.rows()[1].fail_count == 1


def test_prices_upsert_and_remove(store):
    store.add_ticker("IDX", "TLKM")
    store.upsert_prices("IDX", "TLKM", [(1, 10.0), (2, 11.0)])
    store.upsert_prices("IDX", "TLKM", [(2, 12.0), (3, 13.0)])
    assert store.prices("IDX", "TLKM") == [(1, 10.0), (2, 12.0), (3, 13.0)]
    assert store.prices("IDX", "TLKM", since=2) == [(2, 12.0), (3, 13.0)]
    store.remove_ticker("IDX", "TLKM")
    assert store.prices("IDX", "TLKM") == []


async def test_price_failure_does_not_fail_forecast(store):
    store.add_ticker("IDX", "TLKM")

    async def fetcher(ex, sym):
        return fc(sym)

    async def bad_prices(ex, sym):
        raise RuntimeError("boom")

    await Updater(store, settings(), fetcher, bad_prices).sweep()
    assert store.rows()[0].status == "ok"
