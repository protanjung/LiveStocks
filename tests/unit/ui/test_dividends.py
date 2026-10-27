from livestocks.domain import CalendarEntry, CalendarKind, Dividend, DividendPayment
from livestocks.ui.components import date_short
from livestocks.ui.dividends import calendar_sections, dividend_card

NOW = 1_790_000_000


def _entry(symbol: str, kind: CalendarKind, name: str | None = "PT Test Tbk") -> CalendarEntry:
    return CalendarEntry("IDX", symbol, name, NOW, NOW + 86400, 10.0, 5.0, kind)


def _dividend(next_ex: int | None, payments: int = 0) -> Dividend:
    history = tuple(DividendPayment(NOW - i, NOW - i + 5, 1.0, "Annual") for i in range(payments))
    return Dividend(
        next_ex=next_ex,
        next_pay=NOW + 5 if next_ex else None,
        next_amount=10.0 if next_ex else None,
        last_ex=NOW - 100,
        last_pay=NOW - 50,
        last_amount=15.0,
        yield_pct=10.8,
        history=history,
    )


class TestCalendarSections:
    def test_stages_follow_the_dividend_cycle(self):
        html = calendar_sections(
            [
                _entry("BUAH", CalendarKind.RECENT),
                _entry("CSRA", CalendarKind.PAYING),
                _entry("SIDO", CalendarKind.UPCOMING),
            ]
        )

        upcoming = html.index("Upcoming Ex Dates")
        paying = html.index("Awaiting Payment Date")
        recent = html.index("Recent Ex Dates")
        assert upcoming < paying < recent

    def test_each_row_links_to_the_detail_page(self):
        html = calendar_sections([_entry("SIDO", CalendarKind.UPCOMING)])

        assert 'href="/t/IDX/SIDO"' in html

    def test_names_are_escaped(self):
        html = calendar_sections([_entry("SIDO", CalendarKind.UPCOMING, "<script>x</script>")])

        assert "&lt;script&gt;" in html
        assert "<script>" not in html

    def test_empty_stage_is_left_out(self):
        html = calendar_sections([_entry("SIDO", CalendarKind.UPCOMING)])

        assert "Awaiting Payment Date" not in html

    def test_no_rows_gives_an_empty_string(self):
        assert calendar_sections([]) == ""


class TestDividendCard:
    def test_announced_ex_date_is_shown(self):
        html = dividend_card(_dividend(next_ex=NOW + 100), NOW)

        assert date_short(NOW + 100) in html
        assert "none announced" not in html

    def test_no_announcement_says_so(self):
        assert "none announced" in dividend_card(_dividend(next_ex=None), NOW)

    def test_history_shows_at_most_eight_payments(self):
        html = dividend_card(_dividend(next_ex=None, payments=12), NOW)

        assert html.count("<tr><td>") == 8

    def test_no_history_leaves_out_the_table(self):
        assert "<table" not in dividend_card(_dividend(next_ex=None), NOW)


class TestFourDates:
    def test_calendar_table_headers_name_the_four_dates_in_order(self):
        html = calendar_sections([_entry("SIDO", CalendarKind.UPCOMING)])

        header = html.index("Cum Date")
        assert (
            header
            < html.index("Ex Date", header)
            < html.index("Recording Date")
            < html.index("Payment Date")
        )

    def test_calendar_row_shows_a_recording_date_next_to_the_ex_date(self):
        entry = CalendarEntry(
            "IDX",
            "SIDO",
            None,
            NOW,
            NOW + 86400 * 10,
            10.0,
            10.8,
            CalendarKind.UPCOMING,
            cum_date=NOW - 86400,
            record_date=NOW + 86400,
        )

        html = calendar_sections([entry])

        assert date_short(NOW + 86400) in html
        assert date_short(NOW - 86400) in html

    def test_detail_card_names_the_four_dates(self):
        html = dividend_card(_dividend(next_ex=NOW + 100), NOW)

        for term in ("Cum Date", "Ex Date", "Recording Date", "Payment Date"):
            assert term in html

    def test_detail_card_history_has_a_recording_date_column(self):
        html = dividend_card(_dividend(next_ex=None, payments=2), NOW)

        assert "Recording Date" in html
