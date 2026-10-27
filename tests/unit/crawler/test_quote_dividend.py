import pytest

from livestocks.crawler.quote_stream import DIVIDEND_KEEP, parse_quote

SIDO = {
    "dividend_ex_date_upcoming": 1793707140,
    "dividend_payment_date_upcoming": 1795175940,
    "dividend_amount_upcoming": 10,
    "dividend_ex_date_recent": 1776686340,
    "dividend_payment_date_recent": 1778155140,
    "dividend_amount_recent": 15,
    "dividends_yield_current": 10.8187134502924,
    "dividend_ex_date_h": [1793707140, 1776686340, None],
    "dividend_payment_date_h": [1795175940, 1778155140, None],
    "dividend_amount_h": [10, 15, 22],
    "dividend_type_h": ["Semi-Annual", "Semi-Annual", None],
}


class TestParseDividend:
    def test_upcoming_and_recent_fields_are_read(self):
        dividend = parse_quote(SIDO).dividend

        assert dividend is not None
        assert dividend.next_ex == 1793707140
        assert dividend.next_pay == 1795175940
        assert dividend.next_amount == 10
        assert dividend.last_pay == 1778155140
        assert dividend.last_amount == 15
        assert dividend.yield_pct == pytest.approx(10.8187134502924)

    def test_history_is_newest_first_and_skips_empty_rows(self):
        dividend = parse_quote(SIDO).dividend

        assert dividend is not None
        assert [p.amount for p in dividend.history] == [10, 15]
        assert dividend.history[0].kind == "Semi-Annual"

    def test_missing_upcoming_fields_leave_next_dates_empty(self):
        dividend = parse_quote(
            {"dividend_ex_date_recent": 1776686340, "dividend_amount_recent": 223.1}
        ).dividend

        assert dividend is not None
        assert dividend.next_ex is None
        assert dividend.next_pay is None
        assert dividend.last_ex == 1776686340
        assert dividend.last_amount == 223.1

    def test_no_dividend_fields_give_none(self):
        assert parse_quote({}).dividend is None

    def test_history_is_capped(self):
        raw = {
            "dividend_ex_date_h": list(range(1, 21)),
            "dividend_payment_date_h": list(range(1, 21)),
            "dividend_amount_h": [1.0] * 20,
            "dividend_type_h": ["Annual"] * 20,
        }

        dividend = parse_quote(raw).dividend

        assert dividend is not None
        assert len(dividend.history) == DIVIDEND_KEEP


class TestRecordingDates:
    def test_history_rows_carry_their_recording_date(self):
        raw = {
            "dividend_ex_date_h": [1793707140, 1776686340],
            "dividend_payment_date_h": [1795175940, 1778155140],
            "dividend_amount_h": [10, 15],
            "dividend_record_date_h": [1793793540, 1776772740],
        }

        dividend = parse_quote(raw).dividend

        assert dividend is not None
        assert [p.record_date for p in dividend.history] == [1793793540, 1776772740]

    def test_upcoming_dividend_moves_the_recent_one_to_index_one(self):
        raw = {
            "dividend_ex_date_upcoming": 1793707140,
            "dividend_ex_date_h": [1793707140, 1776686340],
            "dividend_record_date_h": [1793793540, 1776772740],
        }

        dividend = parse_quote(raw).dividend

        assert dividend is not None
        assert dividend.next_record == 1793793540
        assert dividend.last_record == 1776772740

    def test_without_an_upcoming_dividend_index_zero_is_the_recent_one(self):
        raw = {
            "dividend_ex_date_recent": 1776686340,
            "dividend_ex_date_h": [1776686340],
            "dividend_record_date_h": [1776772740],
        }

        dividend = parse_quote(raw).dividend

        assert dividend is not None
        assert dividend.next_record is None
        assert dividend.last_record == 1776772740

    def test_missing_record_dates_stay_none(self):
        raw = {"dividend_ex_date_recent": 1776686340, "dividend_amount_recent": 15.0}

        dividend = parse_quote(raw).dividend

        assert dividend is not None
        assert dividend.last_record is None
