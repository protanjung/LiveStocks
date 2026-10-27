from datetime import date, datetime

from livestocks.domain import CalendarEntry, CalendarKind
from livestocks.ui.dividends import MAX_CHIPS, month_grid, month_label, month_of


def _ts(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, 12).timestamp())


def _entry(symbol: str, ex: int | None, pay: int | None) -> CalendarEntry:
    return CalendarEntry("IDX", symbol, None, ex, pay, 10.0, 5.0, CalendarKind.UPCOMING)


class TestMonthOf:
    def test_zero_offset_is_the_current_month(self):
        assert month_of(date(2026, 10, 27), 0) == (2026, 10)

    def test_offsets_carry_across_year_boundaries(self):
        assert month_of(date(2026, 10, 27), 3) == (2027, 1)
        assert month_of(date(2026, 1, 5), -1) == (2025, 12)

    def test_label_names_the_month(self):
        assert month_label(2026, 11) == "November 2026"


class TestMonthGrid:
    def test_ex_and_pay_dates_are_marked_on_their_day(self):
        entry = _entry("SIDO", ex=_ts(2026, 11, 3), pay=_ts(2026, 11, 20))

        html = month_grid([entry], 2026, 11, date(2026, 10, 27))

        assert "EX SIDO" in html
        assert "PAY SIDO" in html

    def test_dates_outside_the_month_are_not_marked(self):
        entry = _entry("SIDO", ex=_ts(2026, 12, 3), pay=None)

        html = month_grid([entry], 2026, 11, date(2026, 10, 27))

        assert "EX SIDO" not in html

    def test_busy_day_collapses_the_rest_into_a_count(self):
        day = _ts(2026, 11, 3)
        entries = [_entry(f"T{i}", ex=day, pay=None) for i in range(MAX_CHIPS + 2)]

        html = month_grid(entries, 2026, 11, date(2026, 10, 27))

        assert f"+{2} more" in html

    def test_symbols_are_escaped(self):
        entry = _entry("<b>", ex=_ts(2026, 11, 3), pay=None)

        html = month_grid([entry], 2026, 11, date(2026, 10, 27))

        assert "&lt;b&gt;" in html
        assert "<b>" not in html
