from livestocks.crawler.quote_stream import parse_quote
from livestocks.ui.components import gauge
from livestocks.ui.financials import compact, fin_table, financial_options


class TestFinancialOptions:
    def test_every_series_builds_a_chart_with_a_forecast_area(self, quote_data):
        extras = parse_quote(quote_data)

        for periods, kind in (
            (extras.eps_fy, "eps"),
            (extras.eps_fq, "eps"),
            (extras.rev_fy, "rev"),
            (extras.rev_fq, "rev"),
        ):
            options = financial_options(periods, kind, dark=True)
            assert len(options["series"]) == 2
            assert len(options["xAxis"]["data"]) == len(periods)
            assert options["series"][1]["markArea"]["data"][0][0]["name"] == "FORECAST"
            assert "Surprise" in fin_table(periods, kind)


class TestCompact:
    def test_eps_keeps_two_decimals(self):
        assert compact(63.5412, "eps") == "63.54"

    def test_revenue_is_abbreviated(self):
        assert compact(136_460_000_000_000, "rev") == "136.46 T"

    def test_missing_value_is_a_dash(self):
        assert compact(None, "eps") == "—"


class TestGauge:
    def test_draws_one_arc_per_rating_with_counts(self, quote_data):
        counts = [n for _, n in parse_quote(quote_data).rating_counts]

        html = gauge(1.22, counts)

        assert html.count("<path") == 5
        assert ">18<" in html
        assert "Strong sell" in html

    def test_no_rating_has_no_arcs(self):
        assert "<path" not in gauge(None)
