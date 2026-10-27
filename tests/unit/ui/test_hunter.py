from datetime import date, datetime

from livestocks.domain import CalendarEntry, CalendarKind, ExDateEvent, HuntStyle, TrapStats
from livestocks.ui.hunter import (
    FILTERS,
    controls,
    howto_card,
    hunt_detail,
    hunt_table,
    key_of,
    ranked,
)

TODAY = date(2026, 10, 27)


def _ts(month: int, day: int) -> int:
    return int(datetime(2026, month, day, 12).timestamp())


def _entry(symbol: str = "SIDO", **fields) -> CalendarEntry:
    base = {
        "exchange": "IDX",
        "symbol": symbol,
        "name": "PT Sido Muncul Tbk",
        "ex_date": _ts(11, 3),
        "pay_date": _ts(11, 20),
        "amount": 10.0,
        "yield_pct": 10.9,
        "kind": CalendarKind.UPCOMING,
        "cum_date": _ts(11, 2),
        "record_date": _ts(11, 4),
        "price": 316.0,
        "avg_volume": 26_500_000.0,
        "payout": 76.0,
        "streak_years": 13,
        "coverage": 1.1,
    }
    base.update(fields)
    return CalendarEntry(**base)


def _trap(drops: list[float]) -> TrapStats:
    return TrapStats(
        tuple(
            ExDateEvent(1_700_000_000 + i, 10.0, 500.0, 500.0 - d, 2) for i, d in enumerate(drops)
        )
    )


class TestRanked:
    def test_best_score_comes_first(self):
        strong = _entry("AAA", trap=_trap([1] * 6))
        weak = _entry("BBB", payout=150.0, streak_years=0, trap=_trap([20] * 6))

        order = [e.symbol for e, _ in ranked([weak, strong], HuntStyle.SHORT, frozenset())]

        assert order == ["AAA", "BBB"]

    def test_an_unscored_row_goes_last(self):
        bare = _entry(
            "ZZZ",
            price=None,
            avg_volume=None,
            payout=None,
            streak_years=None,
            coverage=None,
            yield_pct=None,
        )

        order = [e.symbol for e, _ in ranked([bare, _entry("AAA")], HuntStyle.SHORT, frozenset())]

        assert order == ["AAA", "ZZZ"]

    def test_past_dividends_are_hidden_unless_asked_for(self):
        past = _entry("OLD", kind=CalendarKind.RECENT)

        assert ranked([past], HuntStyle.SHORT, frozenset()) == []
        assert len(ranked([past], HuntStyle.SHORT, frozenset({"past"}))) == 1

    def test_payout_filter_drops_high_payouts_and_unknown_ones(self):
        rows = [_entry("OK", payout=50.0), _entry("HI", payout=131.0), _entry("NA", payout=None)]

        kept = [e.symbol for e, _ in ranked(rows, HuntStyle.SHORT, frozenset({"payout"}))]

        assert kept == ["OK"]

    def test_streak_filter_needs_three_years(self):
        rows = [_entry("LONG", streak_years=5), _entry("NEW", streak_years=1)]

        kept = [e.symbol for e, _ in ranked(rows, HuntStyle.SHORT, frozenset({"streak"}))]

        assert kept == ["LONG"]

    def test_event_yield_filter_needs_two_percent(self):
        rows = [_entry("RICH", amount=10.0), _entry("POOR", amount=1.0)]

        kept = [e.symbol for e, _ in ranked(rows, HuntStyle.SHORT, frozenset({"event"}))]

        assert kept == ["RICH"]

    def test_trap_filter_hides_medium_and_high_risk(self):
        rows = [
            _entry("LOW", trap=_trap([1] * 6)),
            _entry("MED", trap=_trap([20, 20, 1, 1, 1, 1])),
            _entry("HIGH", trap=_trap([20] * 6)),
            _entry("NEW"),
        ]

        kept = {e.symbol for e, _ in ranked(rows, HuntStyle.SHORT, frozenset({"trap"}))}

        assert kept == {"LOW", "NEW"}

    def test_style_changes_the_order(self):
        steady = _entry("STEADY", yield_pct=6.0, streak_years=25, amount=1.0)
        flashy = _entry("FLASHY", yield_pct=2.0, streak_years=1, amount=30.0)

        short = [e.symbol for e, _ in ranked([steady, flashy], HuntStyle.SHORT, frozenset())]
        long = [e.symbol for e, _ in ranked([steady, flashy], HuntStyle.LONG, frozenset())]

        assert short[0] == "FLASHY"
        assert long[0] == "STEADY"


class TestControls:
    def test_current_style_and_view_are_pressed(self):
        html = controls(HuntStyle.LONG, "hunt", frozenset(), False)

        assert 'data-key="long" aria-pressed="true"' in html
        assert 'data-key="short" aria-pressed="false"' in html
        assert 'data-key="hunt" aria-pressed="true"' in html

    def test_active_filters_are_pressed(self):
        html = controls(HuntStyle.SHORT, "hunt", frozenset({"payout"}), False)

        assert 'data-key="payout" aria-pressed="true"' in html
        assert 'data-key="streak" aria-pressed="false"' in html

    def test_every_filter_has_a_chip_in_the_hunt_view(self):
        html = controls(HuntStyle.SHORT, "hunt", frozenset(), False)

        for key, _ in FILTERS:
            assert f'data-key="{key}"' in html

    def test_month_view_has_no_filter_chips(self):
        assert "fchip" not in controls(HuntStyle.SHORT, "month", frozenset(), False)

    def test_help_button_reports_whether_the_guide_is_open(self):
        assert 'aria-expanded="true"' in controls(HuntStyle.SHORT, "hunt", frozenset(), True)
        assert 'aria-expanded="false"' in controls(HuntStyle.SHORT, "hunt", frozenset(), False)


class TestHuntTable:
    def _html(self, entry: CalendarEntry | None = None, selected: str | None = None) -> str:
        rows = ranked([entry or _entry()], HuntStyle.SHORT, frozenset())
        return hunt_table(rows, selected, TODAY)

    def test_empty_list_says_why(self):
        assert "No dividend matches these filters" in hunt_table([], None, TODAY)

    def test_row_is_clickable_by_key(self):
        assert 'data-act="select" data-key="IDX:SIDO"' in self._html()

    def test_selected_row_is_marked(self):
        html = self._html(selected="IDX:SIDO")

        assert 'aria-selected="true"' in html
        assert "hrow sel" in html

    def test_four_dates_are_drawn_as_dots(self):
        html = self._html()

        for letter in ("C", "E", "R", "P"):
            assert f">{letter}</span>" in html

    def test_estimated_dates_say_so_in_their_tooltip(self):
        html = self._html()

        assert "Cum Date: " in html
        assert "(est.)" in html

    def test_a_real_recording_date_is_not_marked_estimated(self):
        derived = self._html(_entry(record_real=False))
        real = self._html(_entry(record_real=True))

        assert derived.count("(est.)") == real.count("(est.)") + 1

    def test_an_ex_date_already_passed_is_noted_in_words(self):
        html = self._html(
            _entry(ex_date=_ts(10, 20), cum_date=_ts(10, 19), record_date=_ts(10, 21))
        )

        assert "Ex passed" in html

    def test_dates_already_past_are_not_drawn_as_dots(self):
        html = self._html(
            _entry(ex_date=_ts(10, 20), cum_date=_ts(10, 19), record_date=_ts(10, 21))
        )

        assert html.count('class="hdot') == 1  # only the upcoming Payment Date

    def test_a_date_beyond_the_window_stays_inside_the_lane(self):
        html = self._html(_entry(pay_date=_ts(12, 30)))

        assert "left:98.00%" in html

    def test_close_dates_are_nudged_apart(self):
        html = self._html()

        assert "margin-left:14px" in html

    def test_company_name_is_escaped(self):
        html = self._html(_entry(name="<img src=x>"))

        assert "&lt;img src=x&gt;" in html
        assert "<img" not in html

    def test_trap_level_is_shown_in_words(self):
        html = self._html(_entry(trap=_trap([20] * 6)))

        assert ">High<" in html

    def test_missing_figures_show_a_dash(self):
        html = self._html(_entry(payout=None, streak_years=None))

        assert ">—</td>" in html


class TestHuntDetail:
    def test_names_the_four_dates(self):
        html = hunt_detail(_entry(), HuntStyle.SHORT)

        for term in ("Cum Date", "Ex Date", "Recording Date", "Payment Date"):
            assert term in html

    def test_derived_dates_are_marked_estimated(self):
        assert "(est.)" in hunt_detail(_entry(record_real=False), HuntStyle.SHORT)

    def test_checklist_has_words_for_each_status(self):
        html = hunt_detail(_entry(payout=131.0), HuntStyle.SHORT)

        assert "✕ Fail" in html
        assert "Payout ratio" in html

    def test_trap_history_lists_events_and_a_summary(self):
        html = hunt_detail(_entry(trap=_trap([20, 20, 1, 1, 1, 1])), HuntStyle.SHORT)

        assert "2 of 6" in html
        assert "Median drop" in html

    def test_missing_history_says_it_is_still_loading(self):
        assert "No Ex Date history yet" in hunt_detail(_entry(), HuntStyle.SHORT)

    def test_links_to_the_ticker_page(self):
        assert 'href="/t/IDX/SIDO"' in hunt_detail(_entry(), HuntStyle.SHORT)

    def test_score_follows_the_style(self):
        entry = _entry(yield_pct=14.0, streak_years=1, amount=30.0)

        assert hunt_detail(entry, HuntStyle.SHORT) != hunt_detail(entry, HuntStyle.LONG)


class TestHowto:
    def test_is_closed_unless_asked_to_open(self):
        assert '<details class="card howto">' in howto_card(False)
        assert '<details class="card howto" open>' in howto_card(True)

    def test_explains_the_four_dates_and_both_styles(self):
        html = howto_card(True)

        for term in ("Cum Date", "Ex Date", "Recording Date", "Payment Date"):
            assert term in html
        assert "Short-term hunter" in html
        assert "Long-term income" in html


def test_key_of_matches_the_ticker_key_format():
    assert key_of(_entry()) == "IDX:SIDO"
