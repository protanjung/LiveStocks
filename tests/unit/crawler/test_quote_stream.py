import json

import pytest
from websockets.asyncio.server import serve

from livestocks.crawler import UpstreamError, quote_stream
from livestocks.crawler.quote_stream import _split, fetch_quote, parse_quote


class TestParseQuote:
    def test_rating_counts_match_tradingview(self, quote_data):
        extras = parse_quote(quote_data)

        assert extras.rating_counts == [
            ("Strong buy", 18),
            ("Buy", 2),
            ("Hold", 2),
            ("Sell", 0),
            ("Strong sell", 1),
        ]

    def test_series_drop_empty_trailing_periods_and_cap_length(self, quote_data):
        extras = parse_quote(quote_data)

        assert extras.eps_fy[-1].label == "2029"  # the empty 2030 entry is dropped
        assert extras.eps_fy[-1].estimate == pytest.approx(174.86)
        assert not extras.eps_fy[-1].reported
        assert len(extras.eps_fy) <= 11
        assert len(extras.eps_fq) <= 16
        assert extras.rev_fy[-1].estimate is not None

    def test_last_reported_year_and_quarter_values(self, quote_data):
        extras = parse_quote(quote_data)

        last_year = [p for p in extras.eps_fy if p.reported][-1]
        quarter = next(p for p in extras.eps_fq if p.label == "2026-Q2")
        assert last_year.label == "2025"
        assert last_year.actual == pytest.approx(179.8286, abs=0.01)
        assert quarter.actual == pytest.approx(63.54, abs=0.1)
        assert quarter.surprise == pytest.approx(0.0924, abs=0.002)

    def test_missing_fields_give_empty_extras(self):
        extras = parse_quote({})

        assert extras.rating_counts is None
        assert extras.eps_fy == ()
        assert extras.rev_fq == ()


class TestSplitFrames:
    def test_splits_length_prefixed_frames(self):
        assert _split('~m~5~m~{"a"}~m~3~m~~h~') == ['{"a"}', "~h~"]


def frame(payload) -> str:
    body = json.dumps(payload)
    return f"~m~{len(body)}~m~{body}"


@pytest.fixture
async def quote_server(monkeypatch):
    """A local websocket server standing in for TradingView; set ``script`` to what it sends."""
    state = {"script": [], "received": []}

    async def handler(connection):
        for _ in range(6):  # the six setup messages every session starts with
            state["received"].append(await connection.recv())
        for message in state["script"]:
            await connection.send(message)
        await connection.wait_closed()

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(
            quote_stream, "WS_URL", f"ws://127.0.0.1:{port}/{{exchange}}-{{symbol}}"
        )
        yield state


class TestFetchQuote:
    async def test_collects_fields_until_quote_completed(self, quote_server):
        quote_server["script"] = [
            frame({"m": "qsd", "p": ["qs", {"n": "IDX:TLKM", "s": "ok", "v": {"a": 1}}]})
            + frame({"m": "qsd", "p": ["qs", {"n": "IDX:TLKM", "s": "ok", "v": {"b": 2}}]})
            + frame({"m": "quote_completed", "p": ["qs", "IDX:TLKM"]}),
        ]

        fields = await fetch_quote("IDX", "TLKM", max_seconds=5)

        assert fields == {"a": 1, "b": 2}

    async def test_session_is_set_up_for_an_anonymous_quote_of_the_symbol(self, quote_server):
        quote_server["script"] = [
            frame({"m": "qsd", "p": ["qs", {"n": "x", "s": "ok", "v": {"a": 1}}]})
            + frame({"m": "quote_completed", "p": ["qs", "x"]}),
        ]

        await fetch_quote("NASDAQ", "AAPL", max_seconds=5)

        setup = " ".join(quote_server["received"])
        assert "unauthorized_user_token" in setup
        assert "NASDAQ:AAPL" in setup

    async def test_heartbeats_are_echoed_back(self, quote_server):
        quote_server["script"] = [
            "~m~4~m~~h~1",
            frame({"m": "qsd", "p": ["qs", {"n": "x", "s": "ok", "v": {"a": 1}}]})
            + frame({"m": "quote_completed", "p": ["qs", "x"]}),
        ]

        assert await fetch_quote("IDX", "TLKM", max_seconds=5) == {"a": 1}

    async def test_error_status_raises_upstream_error(self, quote_server):
        quote_server["script"] = [
            frame({"m": "qsd", "p": ["qs", {"n": "IDX:ZZZZ", "s": "error", "v": {}}]})
        ]

        with pytest.raises(UpstreamError, match="status"):
            await fetch_quote("IDX", "ZZZZ", max_seconds=5)

    async def test_missing_completion_times_out_as_upstream_error(self, quote_server):
        quote_server["script"] = []

        with pytest.raises(UpstreamError, match="websocket error"):
            await fetch_quote("IDX", "TLKM", max_seconds=0.2)

    async def test_connection_failure_raises_upstream_error(self, monkeypatch):
        monkeypatch.setattr(quote_stream, "WS_URL", "ws://127.0.0.1:1/{exchange}-{symbol}")

        with pytest.raises(UpstreamError, match="websocket error"):
            await fetch_quote("IDX", "TLKM", max_seconds=2)
