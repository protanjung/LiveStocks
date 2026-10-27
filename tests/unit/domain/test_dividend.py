from livestocks.domain import Dividend


def _dividend(next_ex: int | None = None, last_pay: int | None = None) -> Dividend:
    return Dividend(
        next_ex=next_ex,
        next_pay=None,
        next_amount=None,
        last_ex=None,
        last_pay=last_pay,
        last_amount=None,
        yield_pct=None,
        history=(),
    )


class TestDividendNextEvent:
    def test_announced_ex_date_is_the_next_event(self):
        assert _dividend(next_ex=200).next_event(100) == 200

    def test_pending_payout_after_a_passed_ex_date_counts(self):
        assert _dividend(last_pay=150).next_event(100) == 150

    def test_earliest_future_date_wins(self):
        assert _dividend(next_ex=300, last_pay=150).next_event(100) == 150

    def test_only_past_dates_give_none(self):
        assert _dividend(next_ex=50, last_pay=60).next_event(100) is None
