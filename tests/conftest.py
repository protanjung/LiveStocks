import json
from collections.abc import Callable
from pathlib import Path

import pytest

from livestocks.domain import Forecast, TrackedTicker

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def forecast_html() -> str:
    return (FIXTURES / "tlkm.html").read_text(encoding="utf8")


@pytest.fixture
def quote_data() -> dict:
    return json.loads((FIXTURES / "tlkm_quote.json").read_text(encoding="utf8"))


@pytest.fixture
def make_forecast() -> Callable[..., Forecast]:
    def factory(symbol: str = "TLKM", **overrides) -> Forecast:
        fields = {
            "exchange": "IDX",
            "symbol": symbol,
            "name": "Telkom",
            "price": 2310.0,
            "change_pct": 1.75,
            "pt_avg": 3394.0,
            "pt_high": 4150.0,
            "pt_low": 2300.0,
            "n_analysts": 22,
            "rating_mark": 1.2,
            "n_ratings": 23,
            "ath": 4850.0,
            "next_earnings": 1793275200,
        }
        fields.update(overrides)
        return Forecast(**fields)

    return factory


@pytest.fixture
def make_ticker(make_forecast) -> Callable[..., TrackedTicker]:
    def factory(
        symbol: str = "TLKM", mark: float | None = 1.2, with_forecast: bool = True
    ) -> TrackedTicker:
        forecast = make_forecast(symbol, rating_mark=mark) if with_forecast else None
        return TrackedTicker("IDX", symbol, None, 0, 1, 0, None, 0, False, forecast, 1)

    return factory


@pytest.fixture
async def store(tmp_path):
    """An initialised Store on a temporary file, closed after the test."""
    from livestocks.storage import Store

    s = Store(tmp_path / "store.db", migrate=False)
    await s.initialize()
    yield s
    await s.close()
