import json
from dataclasses import replace

from livestocks.crawler.quote_stream import parse_quote
from livestocks.domain import Dividend, DividendPayment
from livestocks.storage.mapping import extras_from_json, extras_to_json


class TestDividendMapping:
    def test_round_trips_dividend_with_history(self, quote_data):
        dividend = Dividend(
            next_ex=1,
            next_pay=2,
            next_amount=3.0,
            last_ex=None,
            last_pay=None,
            last_amount=None,
            yield_pct=4.0,
            history=(DividendPayment(1, 2, 3.0, "Annual"),),
        )
        extras = replace(parse_quote(quote_data), dividend=dividend)

        assert extras_from_json(extras_to_json(extras)) == extras

    def test_text_written_before_dividends_loads_with_none(self, quote_data):
        data = json.loads(extras_to_json(parse_quote(quote_data)))
        del data["dividend"]

        assert extras_from_json(json.dumps(data)).dividend is None
