import pytest

from livestocks.tickers import parse_ticker


@pytest.mark.parametrize(
    "raw,expected",
    [("tlkm", ("IDX", "TLKM")), (" IDX:tlkm ", ("IDX", "TLKM")), ("nasdaq:aapl", ("NASDAQ", "AAPL")), ("BRK.B", ("IDX", "BRK.B"))],
)
def test_parse_ok(raw, expected):
    assert parse_ticker(raw, "IDX") == expected


@pytest.mark.parametrize("raw", ["", "  ", "a b", "IDX:", ":TLKM", "../etc", "X" * 30])
def test_parse_bad(raw):
    with pytest.raises(ValueError):
        parse_ticker(raw, "IDX")
