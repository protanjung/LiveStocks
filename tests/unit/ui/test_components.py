import pytest

from livestocks.ui.components import dist_card, duration, kpi_strip, price_fmt, rate_pill


class TestPriceFmt:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(2310.0, "2,310"), (3394.09, "3,394"), (333.63, "333.63"), (None, "—")],
    )
    def test_whole_numbers_for_large_prices_and_decimals_for_small_ones(self, value, expected):
        assert price_fmt(value) == expected


class TestDuration:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [(0, "now"), (30, "<1m"), (3 * 3600 + 5 * 60, "3h 05m"), (None, "—")],
    )
    def test_formats_countdowns(self, seconds, expected):
        assert duration(seconds) == expected


class TestRatePill:
    def test_missing_rating_shows_a_dash(self):
        assert "—" in rate_pill(None)

    def test_buy_rating_uses_the_buy_tone_class(self):
        assert 'class="rate buy"' in rate_pill(1.2)


class TestKpiStrip:
    def test_empty_table_does_not_crash(self):
        assert "Tracked tickers" in kpi_strip([])


class TestDistCard:
    def test_sell_and_strong_sell_are_separate_rows(self, make_ticker):
        rows = [make_ticker("A", 1.2), make_ticker("B", 3.8), make_ticker("C", 4.8)]

        html = dist_card(rows)

        assert "Strong sell" in html
        assert html.count('<div><span><i style="background:') == 5

    def test_no_ratings_renders_nothing(self):
        assert dist_card([]) == ""
