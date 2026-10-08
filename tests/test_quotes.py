import json
from pathlib import Path

import pytest

from livestocks.config import Settings
from livestocks.quotes import _split, parse_quote
from livestocks.store import Store
from livestocks.updater import Updater

from .test_store_updater import fc

QUOTE = json.loads((Path(__file__).parent / "fixtures" / "tlkm_quote.json").read_text())


def test_parse_ratings_match_tradingview():
    x = parse_quote(QUOTE)
    assert x.rating_counts == [("Strong buy", 18), ("Buy", 2), ("Hold", 2), ("Sell", 0), ("Strong sell", 1)]


def test_parse_series():
    x = parse_quote(QUOTE)
    assert x.eps_fy[-1].label == "2029" and x.eps_fy[-1].estimate == pytest.approx(174.86)  # empty 2030 dropped
    assert x.eps_fy[-1].actual is None and not x.eps_fy[-1].reported
    last_reported = [p for p in x.eps_fy if p.reported][-1]
    assert last_reported.label == "2025" and last_reported.actual == pytest.approx(179.8286, abs=0.01)
    assert len(x.eps_fy) <= 11 and len(x.eps_fq) <= 16
    assert x.rev_fy[-1].estimate is not None
    q = [p for p in x.eps_fq if p.label == "2026-Q2"][0]
    assert q.actual == pytest.approx(63.54, abs=0.1) and q.surprise == pytest.approx(0.0924, abs=0.002)


def test_parse_missing_fields():
    x = parse_quote({})
    assert x.rating_counts is None and x.eps_fy == () and x.rev_fq == ()


def test_split_frames():
    assert _split('~m~5~m~{"a"}~m~3~m~~h~') == ['{"a"}', "~h~"]


def test_store_extras_roundtrip():
    s = Store(":memory:")
    s.add_ticker("IDX", "TLKM")
    x = parse_quote(QUOTE)
    s.save_extras("IDX", "TLKM", x, now=5)
    assert s.extras("IDX", "TLKM") == (5, x)
    s.remove_ticker("IDX", "TLKM")
    assert s.extras("IDX", "TLKM") is None


def test_queue_missing_extras():
    s = Store(":memory:")
    s.add_ticker("IDX", "A")
    s.add_ticker("IDX", "B")
    s._db.execute("UPDATE tickers SET last_fetch = 100, next_fetch = 99999")
    s.save_extras("IDX", "A", parse_quote(QUOTE))
    s.queue_missing_extras()
    assert s.due(now=1) == [("IDX", "B")]


async def test_extras_failure_does_not_fail_forecast():
    s = Store(":memory:")
    s.add_ticker("IDX", "TLKM")

    async def fetcher(ex, sym):
        return fc(sym)

    async def bad_extras(ex, sym):
        raise RuntimeError("boom")

    await Updater(s, Settings(jitter_max=0), fetcher, None, bad_extras).sweep()
    assert s.rows()[0].status == "ok" and s.extras("IDX", "TLKM") is None


async def test_extras_saved_on_success():
    s = Store(":memory:")
    s.add_ticker("IDX", "TLKM")

    async def fetcher(ex, sym):
        return fc(sym)

    async def extras(ex, sym):
        return parse_quote(QUOTE)

    await Updater(s, Settings(jitter_max=0), fetcher, None, extras).sweep()
    assert s.extras("IDX", "TLKM")[1].strong_buy == 18


def test_financial_options_build():
    from livestocks.ui.components import gauge
    from livestocks.ui.financials import financial_options, fin_table

    x = parse_quote(QUOTE)
    for periods, kind in ((x.eps_fy, "eps"), (x.eps_fq, "eps"), (x.rev_fy, "rev"), (x.rev_fq, "rev")):
        o = financial_options(periods, kind, True)
        assert len(o["series"]) == 2 and len(o["xAxis"]["data"]) == len(periods)
        assert o["series"][1]["markArea"]["data"][0][0]["name"] == "FORECAST"
        assert "Surprise" in fin_table(periods, kind)
    html = gauge(1.22, [n for _, n in x.rating_counts])
    assert html.count("<path") == 5 and ">18<" in html and "Strong sell" in html
    assert "<path" not in gauge(None)
