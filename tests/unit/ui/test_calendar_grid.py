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


class TestMonthAgenda:
    def test_empty_month_says_so_in_words(self):
        html = month_grid([], 2026, 11, date(2026, 10, 27))

        assert "No dividend dates in November." in html

    def test_today_is_marked_for_assistive_technology(self):
        html = month_grid(
            [_entry("SIDO", ex=_ts(2026, 11, 3), pay=None)], 2026, 11, date(2026, 11, 3)
        )

        assert 'aria-current="date"' in html

    def test_day_label_counts_its_events(self):
        html = month_grid(
            [_entry("SIDO", ex=_ts(2026, 11, 3), pay=None)], 2026, 11, date(2026, 10, 27)
        )

        assert 'aria-label="3 November, 1 event"' in html

    def test_agenda_lists_only_days_with_events(self):
        html = month_grid(
            [_entry("SIDO", ex=_ts(2026, 11, 3), pay=None)], 2026, 11, date(2026, 10, 27)
        )

        assert '<ol class="cal-agenda">' in html
        assert '<time datetime="2026-11-03">' in html
        # Ex Date plus the derived Cum Date (day before) and Recording Date (day after): three days
        assert html.count('<li class="cal-day-row">') == 3

    def test_legend_explains_both_chips(self):
        html = month_grid([], 2026, 11, date(2026, 10, 27))

        assert "Cum Date" in html
        assert "Ex Date" in html
        assert "Recording Date" in html
        assert "Payment Date" in html


class TestTradingDaysOnly:
    def test_grid_has_five_weekday_headers_and_no_weekend_cells(self):
        marks = [_entry("SIDO", ex=_ts(2026, 11, 3), pay=None)]

        grid = month_grid(marks, 2026, 11, date(2026, 10, 27))

        assert grid.count('class="cal-head"') == 5

    def test_weekend_payment_date_is_named_below_the_grid(self):
        saturday = _ts(2026, 11, 7)  # a Saturday
        html = month_grid([_entry("SIDO", ex=None, pay=saturday)], 2026, 11, date(2026, 10, 27))

        assert "Also on a weekend" in html
        assert "Sat 07 Nov" in html
        assert "PAY SIDO" in html

    def test_no_weekend_note_when_every_date_is_a_trading_day(self):
        html = month_grid(
            [_entry("SIDO", ex=_ts(2026, 11, 3), pay=None)], 2026, 11, date(2026, 10, 27)
        )

        assert "Also on a weekend" not in html

    def test_chips_carry_the_full_term_in_their_tooltip(self):
        html = month_grid(
            [_entry("SIDO", ex=_ts(2026, 11, 3), pay=None)], 2026, 11, date(2026, 10, 27)
        )

        assert 'title="Ex Date · SIDO"' in html
        assert 'title="Recording Date · SIDO"' in html
        assert 'title="Cum Date · SIDO"' in html
