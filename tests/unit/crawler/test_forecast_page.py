import httpx
import pytest
import respx

from livestocks.crawler import NotFoundError, ParseError, UpstreamError
from livestocks.crawler.forecast_page import fetch_forecast, parse_html


class TestParseHtml:
    def test_extracts_every_field_from_the_saved_page(self, forecast_html):
        f = parse_html(forecast_html, "IDX", "TLKM")

        assert f.pt_avg == pytest.approx(3394.09, abs=0.01)
        assert (f.pt_high, f.pt_low, f.price, f.ath) == (4150, 2300, 2310, 4850)
        assert (f.n_analysts, f.n_ratings) == (22, 23)
        assert f.rating_mark == pytest.approx(1.217, abs=0.001)
        assert f.next_earnings == 1793275200
        assert f.name
        assert "Telkom" in f.name

    def test_page_without_data_blocks_raises_parse_error(self):
        with pytest.raises(ParseError):
            parse_html("<html>nothing</html>", "IDX", "X")


class TestFetchForecast:
    @respx.mock
    async def test_returns_parsed_forecast_on_200(self, forecast_html):
        respx.get(url__regex=r".*IDX-TLKM.*").mock(
            return_value=httpx.Response(200, text=forecast_html)
        )

        async with httpx.AsyncClient() as client:
            f = await fetch_forecast(client, "IDX", "TLKM")

        assert f.symbol == "TLKM"
        assert f.pt_high == 4150

    @respx.mock
    async def test_404_raises_not_found_without_retrying(self):
        route = respx.get(url__regex=r".*").mock(return_value=httpx.Response(404))

        async with httpx.AsyncClient() as client:
            with pytest.raises(NotFoundError):
                await fetch_forecast(client, "IDX", "ZZZZ")

        assert route.call_count == 1

    @respx.mock
    async def test_429_is_retried_then_raises_upstream_error(self):
        route = respx.get(url__regex=r".*").mock(return_value=httpx.Response(429))

        async with httpx.AsyncClient() as client:
            with pytest.raises(UpstreamError, match="429"):
                await fetch_forecast(client, "IDX", "TLKM", retries=2)

        assert route.call_count == 3
