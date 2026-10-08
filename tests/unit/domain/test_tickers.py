import pytest

from livestocks.domain import InvalidTickerError, TickerId, parse_ticker


class TestParseTicker:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("tlkm", TickerId("IDX", "TLKM")),
            (" IDX:tlkm ", TickerId("IDX", "TLKM")),
            ("nasdaq:aapl", TickerId("NASDAQ", "AAPL")),
            ("BRK.B", TickerId("IDX", "BRK.B")),
        ],
    )
    def test_valid_text_is_normalised(self, raw, expected):
        assert parse_ticker(raw, "IDX") == expected

    @pytest.mark.parametrize("raw", ["", "  ", "a b", "IDX:", ":TLKM", "../etc", "X" * 30])
    def test_invalid_text_raises_invalid_ticker_error(self, raw):
        with pytest.raises(InvalidTickerError):
            parse_ticker(raw, "IDX")

    def test_invalid_ticker_error_is_a_value_error(self):
        with pytest.raises(ValueError, match="not a valid ticker"):
            parse_ticker("a b", "IDX")

    def test_key_joins_exchange_and_symbol(self):
        assert parse_ticker("nyse:ko", "IDX").key == "NYSE:KO"
