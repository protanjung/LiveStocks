import asyncio

import httpx
import pytest
from fastapi import FastAPI

from livestocks.api import build_router, register_error_handlers
from livestocks.config import Settings
from livestocks.crawler import CrawlResult, NotFoundError, UpstreamError
from livestocks.crawler.quote_stream import parse_quote
from livestocks.services import ForecastService, Updater
from livestocks.storage import Store


@pytest.fixture
async def api(make_forecast, quote_data):
    """A bare FastAPI app with the real router and service; ``plan`` scripts the crawler."""
    store = Store(":memory:")
    settings = Settings(jitter_max=0, refresh_interval=3600, poll_interval=60, api_wait_seconds=2)
    plan: dict = {"calls": [], "delay": None, "error": None}

    async def crawler(exchange, symbol):
        plan["calls"].append(symbol)
        if plan["delay"] is not None:
            await plan["delay"].wait()
        if plan["error"] is not None:
            raise plan["error"]
        return CrawlResult(make_forecast(symbol, exchange=exchange), extras=parse_quote(quote_data))

    updater = Updater(store, settings, crawler)
    service = ForecastService(store, updater, settings)
    app = FastAPI()
    app.include_router(build_router(service), prefix="/api/v1")
    register_error_handlers(app)
    await updater.start()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, plan, settings
    await updater.stop()
    store.close()


class TestForecastEndpoint:
    async def test_first_request_tracks_the_ticker_and_returns_its_forecast(self, api):
        client, plan, _ = api

        response = await client.get("/api/v1/forecast/tlkm")

        body = response.json()
        assert response.status_code == 200
        assert body["ticker"] == {
            "exchange": "IDX",
            "symbol": "TLKM",
            "name": "Telkom",
        }
        assert body["created"] is True
        assert body["status"] == "ok"
        assert body["stale"] is False
        assert plan["calls"] == ["TLKM"]

    async def test_response_carries_price_target_rating_and_estimates(self, api):
        client, _, _ = api

        body = (await client.get("/api/v1/forecast/IDX:TLKM")).json()

        assert body["price"]["last"] == 2310.0
        assert body["price_target"]["average"] == 3394.0
        assert body["price_target"]["upside_pct"] == pytest.approx((3394 / 2310 - 1) * 100)
        assert body["rating"]["label"] == "Strong buy"
        assert body["rating"]["counts"] == {
            "strong_buy": 18,
            "buy": 2,
            "hold": 2,
            "sell": 0,
            "strong_sell": 1,
        }
        assert body["estimates"]["eps"]["annual"][-1]["period"] == "2029"
        assert body["estimates"]["revenue"]["quarterly"]
        assert body["fetched_at"].endswith("Z")

    async def test_second_request_is_served_from_storage_without_crawling(self, api):
        client, plan, _ = api
        await client.get("/api/v1/forecast/TLKM")

        second = (await client.get("/api/v1/forecast/TLKM")).json()

        assert second["created"] is False
        assert plan["calls"] == ["TLKM"]

    async def test_exchange_prefix_selects_the_exchange(self, api):
        client, _, _ = api

        body = (await client.get("/api/v1/forecast/nasdaq:aapl")).json()

        assert body["ticker"]["exchange"] == "NASDAQ"
        assert body["ticker"]["symbol"] == "AAPL"

    async def test_concurrent_first_requests_trigger_a_single_crawl(self, api):
        client, plan, _ = api
        plan["delay"] = asyncio.Event()

        pending = [asyncio.create_task(client.get("/api/v1/forecast/TLKM")) for _ in range(3)]
        await asyncio.sleep(0.05)
        plan["delay"].set()
        responses = await asyncio.gather(*pending)

        assert [r.status_code for r in responses] == [200, 200, 200]
        assert plan["calls"] == ["TLKM"]


class TestErrorAnswers:
    async def test_malformed_ticker_is_422_with_an_error_body(self, api):
        client, _, _ = api

        response = await client.get("/api/v1/forecast/a%20b")

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_ticker"
        assert "not a valid ticker" in response.json()["detail"]

    async def test_unknown_ticker_is_404(self, api):
        client, plan, _ = api
        plan["error"] = NotFoundError("not found on TradingView")

        response = await client.get("/api/v1/forecast/ZZZZ")

        assert response.status_code == 404
        assert response.json() == {"code": "ticker_not_found", "detail": "not found on TradingView"}

    async def test_upstream_failure_is_502(self, api):
        client, plan, _ = api
        plan["error"] = UpstreamError("HTTP 503")

        response = await client.get("/api/v1/forecast/TLKM")

        assert response.status_code == 502
        assert response.json()["code"] == "upstream_error"

    async def test_a_known_failing_ticker_answers_immediately(self, api):
        client, plan, _ = api
        plan["error"] = NotFoundError("not found on TradingView")
        await client.get("/api/v1/forecast/ZZZZ")
        plan["calls"].clear()

        response = await client.get("/api/v1/forecast/ZZZZ")

        assert response.status_code == 404
        assert plan["calls"] == []

    async def test_slow_first_crawl_is_504_and_the_data_arrives_later(self, api):
        client, plan, settings = api
        plan["delay"] = asyncio.Event()
        settings.api_wait_seconds = 0.05

        response = await client.get("/api/v1/forecast/TLKM")

        assert response.status_code == 504
        assert response.json()["code"] == "crawl_timeout"
        plan["delay"].set()
        later = await client.get("/api/v1/forecast/TLKM")
        assert later.status_code == 200
        assert plan["calls"] == ["TLKM"]


class TestOpenApi:
    async def test_schema_documents_the_endpoint_and_its_error_bodies(self, api):
        client, _, _ = api
        app: FastAPI = client._transport.app  # type: ignore[attr-defined]

        schema = app.openapi()
        operation = schema["paths"]["/api/v1/forecast/{ticker}"]["get"]

        assert set(operation["responses"]) >= {"200", "404", "422", "502", "504"}
        assert "ForecastResponse" in schema["components"]["schemas"]
        assert "ErrorResponse" in schema["components"]["schemas"]
