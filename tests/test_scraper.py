from pathlib import Path

import httpx
import pytest
import respx

from livestocks.scraper import NotFoundError, ParseError, ScrapeError, fetch_forecast, parse_html

FIXTURE = Path(__file__).parent / "fixtures" / "tlkm.html"


def test_parse_fixture():
    f = parse_html(FIXTURE.read_text(encoding="utf8"), "IDX", "TLKM")
    assert f.pt_avg == pytest.approx(3394.09, abs=0.01)
    assert f.pt_high == 4150
    assert f.pt_low == 2300
    assert f.price == 2310
    assert f.n_analysts == 22
    assert f.n_ratings == 23
    assert f.rating_mark == pytest.approx(1.217, abs=0.001)
    assert f.ath == 4850
    assert f.next_earnings == 1793275200
    assert f.name and "Telkom" in f.name


def test_parse_missing_blocks():
    with pytest.raises(ParseError):
        parse_html("<html>nothing</html>", "IDX", "X")


@respx.mock
async def test_fetch_ok():
    respx.get(url__regex=r".*IDX-TLKM.*").mock(
        return_value=httpx.Response(200, text=FIXTURE.read_text(encoding="utf8"))
    )
    async with httpx.AsyncClient() as c:
        f = await fetch_forecast(c, "IDX", "TLKM")
    assert f.symbol == "TLKM" and f.pt_high == 4150


@respx.mock
async def test_fetch_404():
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as c:
        with pytest.raises(NotFoundError):
            await fetch_forecast(c, "IDX", "ZZZZ")


@respx.mock
async def test_fetch_429_retries_then_fails(monkeypatch):
    async def no_sleep(_): ...

    monkeypatch.setattr("livestocks.scraper.asyncio.sleep", no_sleep)
    route = respx.get(url__regex=r".*").mock(return_value=httpx.Response(429))
    async with httpx.AsyncClient() as c:
        with pytest.raises(ScrapeError, match="429"):
            await fetch_forecast(c, "IDX", "TLKM", retries=2)
    assert route.call_count == 3
