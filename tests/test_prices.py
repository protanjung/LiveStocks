import pytest

from livestocks.prices import PriceError, parse_chart, yahoo_symbol


def test_yahoo_symbol():
    assert yahoo_symbol("IDX", "TLKM") == "TLKM.JK"
    assert yahoo_symbol("NASDAQ", "AAPL") == "AAPL"
    assert yahoo_symbol("NYSE", "BRK.B") == "BRK-B"
    assert yahoo_symbol("WAT", "X") is None


def test_parse_chart_skips_null_closes():
    data = {"chart": {"result": [{"timestamp": [1, 2, 3], "indicators": {"quote": [{"close": [1.5, None, 2.5]}]}}]}}
    assert parse_chart(data) == [(1, 1.5), (3, 2.5)]


def test_parse_chart_bad():
    with pytest.raises(PriceError):
        parse_chart({"chart": {"result": None}})
