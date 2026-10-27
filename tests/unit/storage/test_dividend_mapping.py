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


class TestRecordingDateMapping:
    def test_recording_dates_round_trip(self, quote_data):
        dividend = Dividend(
            next_ex=1,
            next_pay=2,
            next_amount=3.0,
            last_ex=None,
            last_pay=None,
            last_amount=None,
            yield_pct=4.0,
            history=(DividendPayment(1, 2, 3.0, "Annual", 5),),
            next_record=5,
            last_record=6,
        )
        extras = replace(parse_quote(quote_data), dividend=dividend)

        restored = extras_from_json(extras_to_json(extras))

        assert restored == extras
        assert restored.dividend.history[0].record_date == 5

    def test_text_written_before_recording_dates_loads_with_none(self, quote_data):
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
        data = json.loads(extras_to_json(replace(parse_quote(quote_data), dividend=dividend)))
        for key in ("next_record", "last_record"):
            del data["dividend"][key]
        del data["dividend"]["history"][0]["record_date"]

        restored = extras_from_json(json.dumps(data))

        assert restored.dividend.next_record is None
        assert restored.dividend.history[0].record_date is None
