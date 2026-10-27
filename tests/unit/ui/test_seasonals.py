from datetime import UTC, datetime

import pytest

from livestocks.domain import PriceBar
from livestocks.ui.seasonals import seasonal_average, seasonal_options, seasonal_returns


def _ts(year: int, month: int) -> int:
    return int(datetime(year, month, 15, tzinfo=UTC).timestamp())


class TestSeasonalReturns:
    def test_month_is_measured_from_prior_december_close(self):
        bars = [
            PriceBar(_ts(2023, 12), 100.0),
            PriceBar(_ts(2024, 1), 110.0),
            PriceBar(_ts(2024, 2), 99.0),
        ]

        returns = seasonal_returns(bars)

        assert returns[2024][0] == pytest.approx(10.0)
        assert returns[2024][1] == pytest.approx(-1.0)
        assert returns[2024][2] is None

    def test_year_without_prior_december_is_dropped(self):
        bars = [PriceBar(_ts(2024, 1), 110.0), PriceBar(_ts(2024, 2), 99.0)]

        assert seasonal_returns(bars) == {}

    def test_keeps_last_close_of_each_month(self):
        bars = [
            PriceBar(_ts(2023, 12), 100.0),
            PriceBar(_ts(2024, 1), 110.0),
            PriceBar(_ts(2024, 1) + 60, 120.0),
        ]

        assert seasonal_returns(bars)[2024][0] == pytest.approx(20.0)


class TestSeasonalAverage:
    def test_averages_each_month_over_years_that_have_it(self):
        by_year = {
            2023: [10.0, None] + [None] * 10,
            2024: [20.0, 5.0] + [None] * 10,
        }

        average = seasonal_average(by_year)

        assert average[:2] == [15.0, 5.0]
        assert average[2] is None

    def test_no_years_gives_all_none(self):
        assert seasonal_average({}) == [None] * 12


class TestSeasonalOptions:
    def test_one_line_per_year_plus_average(self):
        bars = [
            PriceBar(_ts(2022, 12), 100.0),
            PriceBar(_ts(2023, 12), 110.0),
            PriceBar(_ts(2024, 6), 121.0),
        ]

        options = seasonal_options(bars, dark=True)

        assert [s["name"] for s in options["series"]] == ["2023", "2024", "Average"]
        assert len(options["xAxis"]["data"]) == 12

    def test_palette_follows_theme(self):
        bars = [PriceBar(_ts(2022, 12), 100.0), PriceBar(_ts(2023, 6), 110.0)]

        dark = seasonal_options(bars, dark=True)["series"][-1]["itemStyle"]["color"]
        light = seasonal_options(bars, dark=False)["series"][-1]["itemStyle"]["color"]

        assert dark != light
