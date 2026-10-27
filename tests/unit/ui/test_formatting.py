import math

import pytest

from livestocks.crawler.quote_stream import parse_quote
from livestocks.ui.chart import COLORS, _target_line
from livestocks.ui.components import ago, big_range, date_short, fmt, price_fmt
from livestocks.ui.financials import financial_options
from livestocks.ui.suggestions import _cost, day_label


class TestNumberFormats:
    @pytest.mark.parametrize("value", [None, math.nan, math.inf, -math.inf])
    def test_fmt_renders_missing_and_non_finite_as_a_dash(self, value):
        assert fmt(value, 2) == "—"

    def test_fmt_groups_thousands_with_the_given_decimals(self):
        assert fmt(1234.5, 1) == "1,234.5"

    @pytest.mark.parametrize("value", [math.nan, math.inf])
    def test_price_fmt_renders_non_finite_as_a_dash(self, value):
        assert price_fmt(value) == "—"

    def test_price_fmt_uses_whole_numbers_from_1000_up(self):
        assert price_fmt(2310.0) == "2,310"

    def test_price_fmt_keeps_two_decimals_below_1000(self):
        assert price_fmt(0.5) == "0.50"


class TestAgo:
    def test_explicit_zero_clock_is_used_not_the_wall_clock(self):
        assert ago(0, now=0) == "just now"

    def test_missing_timestamp_is_a_dash(self):
        assert ago(None) == "—"


class TestDateShort:
    def test_out_of_range_timestamp_is_a_dash(self):
        assert date_short(10**20) == "—"

    def test_zero_is_a_dash(self):
        assert date_short(0) == "—"

    def test_formats_day_month_and_year(self):
        assert date_short(1793707140).endswith("2026")


class TestGuardsAgainstZeroPrice:
    def test_big_range_with_zero_price_shows_the_unavailable_note(self, make_forecast):
        html = big_range(make_forecast(price=0.0))

        assert "unavailable" in html

    def test_target_line_with_zero_price_does_not_divide_by_zero(self):
        col = COLORS[True]

        lines = _target_line("Max", 0, 1, 0.0, 10.0, "#fff", col)

        assert lines[0]["name"] == "Max"


class TestSuggestionValues:
    def test_boolean_lots_are_not_counted(self):
        assert _cost({"entry": {"price": 1000}, "lots": True}) == ""

    def test_whole_lots_price_the_order(self):
        assert _cost({"entry": {"price": 1000}, "lots": 2}) == "≈ Rp 200,000"

    def test_day_label_returns_plain_text_for_non_dates(self):
        assert day_label("not-a-date") == "not-a-date"

    def test_day_label_formats_a_trading_date(self):
        assert day_label("2026-10-12").endswith("12 Oct")


class TestFinancialTooltipEscaping:
    def test_axis_label_is_escaped_before_it_reaches_the_tooltip(self, quote_data):
        periods = parse_quote(quote_data).eps_fy
        tooltip = financial_options(periods, "eps", dark=True)["tooltip"][":formatter"]

        assert "esc(ps[0].axisValue)" in tooltip
        assert "&lt;" in tooltip
