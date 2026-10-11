import copy

import httpx
import pytest
from fastapi import FastAPI

from livestocks.api import build_suggestions_router, register_error_handlers
from livestocks.config import Settings
from livestocks.services import SuggestionService

TOKEN = "s3cret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

BUY_ORDER = {
    "side": "BUY",
    "stock": "BBRI",
    "start_date": "2026-10-12",
    "end_date": "2026-10-12",
    "condition": {"type": "price", "operator": "<=", "value": 3090},
    "execute": {"by": "price", "price": 3090},
    "qty_lots": 3,
}

PAYLOAD = {
    "schema": "idx-suggestions/v1",
    "date": "2026-10-12",
    "generated_at": "2026-10-12T08:55:00+07:00",
    "market": {"ihsg_last": 6093.75, "summary": "IHSG +1.04% to 6,093.75."},
    "suggestions": [
        {
            "ticker": "BBRI",
            "name": "Bank Rakyat Indonesia Tbk",
            "held": True,
            "action": "BUY",
            "lots": 3,
            "reference_price": 3100,
            "reference_source": "search",
            "entry": {"low": 3070, "high": 3100, "price": 3090},
            "tp1": 3600,
            "tp2": 3850,
            "stop": 2990,
            "stop_pct": -3.2,
            "rr": 5.1,
            "post_trade_weight_pct": 12.4,
            "verified": True,
            "reason": "Below consensus target.",
            "auto_order": BUY_ORDER,
            "exits": [
                {
                    **BUY_ORDER,
                    "label": "TP1",
                    "side": "SELL",
                    "condition": {"type": "price", "operator": ">=", "value": 3600},
                    "execute": {"by": "price", "price": 3600},
                }
            ],
        },
        {
            "ticker": "TLKM",
            "name": "Telkom Indonesia Tbk",
            "held": True,
            "action": "HOLD",
            "lots": 0,
            "reference_price": None,
            "reference_source": None,
            "entry": {"low": None, "high": None, "price": None},
            "tp1": None,
            "tp2": None,
            "stop": None,
            "stop_pct": None,
            "rr": None,
            "post_trade_weight_pct": None,
            "verified": False,
            "reason": "No fresh price found.",
            "auto_order": None,
            "exits": [],
        },
    ],
    "disclaimer": "Informational only, not financial advice.",
}


def payload(**changes):
    body = copy.deepcopy(PAYLOAD)
    body.update(changes)
    return body


@pytest.fixture
async def client(store):
    settings = Settings(api_token=TOKEN)
    app = FastAPI()
    app.include_router(
        build_suggestions_router(SuggestionService(store), settings), prefix="/api/v1"
    )
    register_error_handlers(app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestDelivery:
    async def test_a_valid_report_is_stored_and_acknowledged(self, client):
        response = await client.post("/api/v1/suggestions", json=PAYLOAD, headers=AUTH)

        body = response.json()
        assert response.status_code == 201
        assert body["date"] == "2026-10-12"
        assert body["count"] == 2
        assert body["received_at"].endswith("Z")

    async def test_delivering_a_date_again_replaces_it(self, client):
        await client.post("/api/v1/suggestions", json=PAYLOAD, headers=AUTH)
        second = payload(market={"ihsg_last": None, "summary": "Second run."})

        await client.post("/api/v1/suggestions", json=second, headers=AUTH)

        days = (await client.get("/api/v1/suggestions", headers=AUTH)).json()
        assert [d["summary"] for d in days] == ["Second run."]

    async def test_missing_or_wrong_token_is_unauthorized(self, client):
        for headers in ({}, {"Authorization": "Bearer nope"}, {"Authorization": TOKEN}):
            response = await client.post("/api/v1/suggestions", json=PAYLOAD, headers=headers)

            assert response.status_code == 401
            assert response.json()["code"] == "unauthorized"

    async def test_without_a_configured_token_delivery_is_disabled(self, store):
        app = FastAPI()
        app.include_router(
            build_suggestions_router(SuggestionService(store), Settings(api_token=None)),
            prefix="/api/v1",
        )
        register_error_handlers(app)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as open_client:
            response = await open_client.post("/api/v1/suggestions", json=PAYLOAD)
            read = await open_client.get("/api/v1/suggestions/latest")

        assert response.status_code == 503
        assert response.json()["code"] == "ingest_disabled"
        assert read.status_code == 404  # reading stays open when no token is configured

    @pytest.mark.parametrize(
        "bad",
        [
            payload(schema="idx-suggestions/v2"),
            payload(date="12-10-2026"),
            payload(suggestions=[{**PAYLOAD["suggestions"][1], "action": "BUY MORE"}]),
            payload(suggestions=[{**PAYLOAD["suggestions"][1], "ticker": "bbca.jk"}]),
        ],
    )
    async def test_a_malformed_report_is_rejected_with_the_problem_named(self, client, bad):
        response = await client.post("/api/v1/suggestions", json=bad, headers=AUTH)

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_payload"
        assert response.json()["detail"]
        assert (await client.get("/api/v1/suggestions", headers=AUTH)).json() == []


class TestReading:
    async def test_latest_returns_the_stored_document_with_its_receive_time(self, client):
        await client.post("/api/v1/suggestions", json=PAYLOAD, headers=AUTH)

        response = await client.get("/api/v1/suggestions/latest", headers=AUTH)

        body = response.json()
        assert response.status_code == 200
        assert body["schema"] == "idx-suggestions/v1"
        assert body["date"] == "2026-10-12"
        assert body["generated_at"] == "2026-10-12T08:55:00+07:00"
        assert body["received_at"].endswith("Z")
        assert [s["ticker"] for s in body["suggestions"]] == ["BBRI", "TLKM"]
        assert body["suggestions"][0]["auto_order"]["condition"]["value"] == 3090
        assert body["suggestions"][0]["exits"][0]["label"] == "TP1"

    async def test_a_date_returns_that_days_report_and_unknown_dates_are_404(self, client):
        await client.post("/api/v1/suggestions", json=PAYLOAD, headers=AUTH)

        found = await client.get("/api/v1/suggestions/2026-10-12", headers=AUTH)
        missing = await client.get("/api/v1/suggestions/2026-10-11", headers=AUTH)

        assert found.status_code == 200
        assert missing.status_code == 404
        assert missing.json()["code"] == "suggestion_not_found"

    async def test_latest_is_404_before_anything_arrives(self, client):
        response = await client.get("/api/v1/suggestions/latest", headers=AUTH)

        assert response.status_code == 404
        assert response.json()["code"] == "suggestion_not_found"

    async def test_a_malformed_date_is_422(self, client):
        response = await client.get("/api/v1/suggestions/yesterday", headers=AUTH)

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_date"

    async def test_the_list_counts_actions_newest_date_first(self, client):
        await client.post("/api/v1/suggestions", json=PAYLOAD, headers=AUTH)
        await client.post("/api/v1/suggestions", json=payload(date="2026-10-09"), headers=AUTH)

        days = (await client.get("/api/v1/suggestions?limit=5", headers=AUTH)).json()

        assert [d["date"] for d in days] == ["2026-10-12", "2026-10-09"]
        assert (days[0]["buy"], days[0]["sell"], days[0]["hold"]) == (1, 0, 1)
        assert days[0]["ihsg_last"] == 6093.75

    async def test_reading_requires_the_token_when_one_is_configured(self, client):
        for path in ("/latest", "/2026-10-12", ""):
            response = await client.get(f"/api/v1/suggestions{path}")

            assert response.status_code == 401


class TestOpenApi:
    async def test_the_suggestion_paths_are_documented(self, client):
        # The bare test app has no docs routes, so read the schema straight from the app.
        schema = client._transport.app.openapi()  # type: ignore[attr-defined]

        assert set(schema["paths"]) == {
            "/api/v1/suggestions",
            "/api/v1/suggestions/latest",
            "/api/v1/suggestions/{day}",
        }
        assert "post" in schema["paths"]["/api/v1/suggestions"]
