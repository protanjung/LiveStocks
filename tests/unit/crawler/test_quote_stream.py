import pytest

from livestocks.crawler.quote_stream import _split, parse_quote


class TestParseQuote:
    def test_rating_counts_match_tradingview(self, quote_data):
        extras = parse_quote(quote_data)

        assert extras.rating_counts == [
            ("Strong buy", 18),
            ("Buy", 2),
            ("Hold", 2),
            ("Sell", 0),
            ("Strong sell", 1),
        ]

    def test_series_drop_empty_trailing_periods_and_cap_length(self, quote_data):
        extras = parse_quote(quote_data)

        assert extras.eps_fy[-1].label == "2029"  # the empty 2030 entry is dropped
        assert extras.eps_fy[-1].estimate == pytest.approx(174.86)
        assert not extras.eps_fy[-1].reported
        assert len(extras.eps_fy) <= 11 and len(extras.eps_fq) <= 16
        assert extras.rev_fy[-1].estimate is not None

    def test_last_reported_year_and_quarter_values(self, quote_data):
        extras = parse_quote(quote_data)

        last_year = [p for p in extras.eps_fy if p.reported][-1]
        quarter = next(p for p in extras.eps_fq if p.label == "2026-Q2")
        assert last_year.label == "2025" and last_year.actual == pytest.approx(179.8286, abs=0.01)
        assert quarter.actual == pytest.approx(63.54, abs=0.1)
        assert quarter.surprise == pytest.approx(0.0924, abs=0.002)

    def test_missing_fields_give_empty_extras(self):
        extras = parse_quote({})

        assert extras.rating_counts is None
        assert extras.eps_fy == () and extras.rev_fq == ()


class TestSplitFrames:
    def test_splits_length_prefixed_frames(self):
        assert _split('~m~5~m~{"a"}~m~3~m~~h~') == ['{"a"}', "~h~"]
