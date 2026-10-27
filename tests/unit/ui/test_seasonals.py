from datetime import UTC, datetime

import pytest

from livestocks.domain import PriceBar
from livestocks.ui.seasonals import (
    DAY_KEYS,
    DAY_MS,
    seasonal_average,
    seasonal_options,
    seasonal_returns,
)


def _ts(year: int, month: int, day: int, hour: int = 12) -> int:
    return int(datetime(year, month, day, hour, tzinfo=UTC).timestamp())


def _slot(month: int, day: int) -> int:
    return DAY_KEYS.index((month, day))


class TestSeasonalReturns:
    def test_day_is_measured_from_prior_year_end_close(self):
        bars = [PriceBar(_ts(2022, 12, 31), 100.0), PriceBar(_ts(2023, 1, 3), 110.0)]

        returns = seasonal_returns(bars)

        assert returns[2023][_slot(1, 3)] == pytest.approx(10.0)

    def test_weekend_repeats_last_close(self):
        bars = [
            PriceBar(_ts(2022, 12, 31), 100.0),
            PriceBar(_ts(2023, 1, 2), 105.0),
            PriceBar(_ts(2023, 1, 4), 110.0),
        ]

        returns = seasonal_returns(bars)

        assert returns[2023][_slot(1, 3)] == pytest.approx(5.0)

    def test_latest_year_is_none_before_first_and_after_last_bar(self):
        bars = [
            PriceBar(_ts(2022, 12, 31), 100.0),
            PriceBar(_ts(2023, 1, 3), 110.0),
            PriceBar(_ts(2023, 3, 10), 120.0),
        ]

        row = seasonal_returns(bars)[2023]

        assert row[_slot(1, 2)] is None
        assert row[_slot(3, 10)] == pytest.approx(20.0)
        assert row[_slot(3, 11)] is None

    def test_earlier_year_fills_to_year_end(self):
        bars = [
            PriceBar(_ts(2022, 12, 31), 100.0),
            PriceBar(_ts(2023, 1, 3), 110.0),
            PriceBar(_ts(2023, 12, 20), 120.0),
            PriceBar(_ts(2024, 1, 5), 125.0),
        ]

        row = seasonal_returns(bars)[2023]

        assert row[_slot(12, 31)] == pytest.approx(20.0)

    def test_year_without_prior_year_end_is_dropped(self):
        bars = [PriceBar(_ts(2023, 1, 3), 110.0), PriceBar(_ts(2023, 2, 1), 99.0)]

        assert seasonal_returns(bars) == {}

    def test_feb_29_carries_feb_28_in_non_leap_year(self):
        bars = [
            PriceBar(_ts(2022, 12, 31), 100.0),
            PriceBar(_ts(2023, 2, 28), 110.0),
            PriceBar(_ts(2023, 3, 1), 121.0),
        ]

        row = seasonal_returns(bars)[2023]

        assert row[_slot(2, 29)] == pytest.approx(10.0)
        assert row[_slot(3, 1)] == pytest.approx(21.0)

    def test_last_close_of_the_same_day_wins(self):
        bars = [
            PriceBar(_ts(2022, 12, 31), 100.0),
            PriceBar(_ts(2023, 1, 3, hour=10), 110.0),
            PriceBar(_ts(2023, 1, 3, hour=15), 120.0),
        ]

        assert seasonal_returns(bars)[2023][_slot(1, 3)] == pytest.approx(20.0)


class TestSeasonalAverage:
    def test_averages_each_day_over_years_that_have_it(self):
        by_year = {
            2023: [10.0, None] + [None] * 364,
            2024: [20.0, 5.0] + [None] * 364,
        }

        average = seasonal_average(by_year)

        assert len(average) == len(DAY_KEYS)
        assert average[0] == pytest.approx(15.0)
        assert average[1] == pytest.approx(5.0)
        assert average[2] is None

    def test_no_years_gives_all_none(self):
        assert seasonal_average({}) == [None] * len(DAY_KEYS)


class TestSeasonalOptions:
    def test_one_line_per_year_plus_average_on_a_time_axis(self):
        bars = [
            PriceBar(_ts(2022, 12, 31), 100.0),
            PriceBar(_ts(2023, 6, 30), 110.0),
            PriceBar(_ts(2024, 6, 28), 121.0),
        ]

        options = seasonal_options(bars, dark=True)

        assert [s["name"] for s in options["series"]] == ["2023", "2024", "Average"]
        assert options["xAxis"]["type"] == "time"

    def test_points_are_timestamp_value_pairs_starting_at_first_bar(self):
        bars = [PriceBar(_ts(2022, 12, 31), 100.0), PriceBar(_ts(2023, 6, 30), 110.0)]

        data = seasonal_options(bars, dark=True)["series"][0]["data"]

        assert data[0] == [DAY_MS[_slot(6, 30)], pytest.approx(10.0)]
        assert all(len(point) == 2 for point in data)

    def test_palette_follows_theme(self):
        bars = [PriceBar(_ts(2022, 12, 31), 100.0), PriceBar(_ts(2023, 6, 30), 110.0)]

        dark = seasonal_options(bars, dark=True)["series"][-1]["itemStyle"]["color"]
        light = seasonal_options(bars, dark=False)["series"][-1]["itemStyle"]["color"]

        assert dark != light
