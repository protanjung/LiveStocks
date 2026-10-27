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

        upcoming = html.index("Upcoming ex-dates")
        paying = html.index("Paying soon")
        recent = html.index("Recently went ex-dividend")
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

        assert "Paying soon" not in html

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
