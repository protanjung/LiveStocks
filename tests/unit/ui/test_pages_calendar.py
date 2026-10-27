from datetime import datetime

import pytest
from tests.unit.ui.app import fakes
from tests.unit.ui.app.sim import simulate

from livestocks.domain import CalendarEntry, CalendarKind, HuntStyle
from livestocks.ui.hunter import apply_action
from livestocks.ui.models import PageState


def _ts(month: int, day: int) -> int:
    return int(datetime(2026, month, day, 12).timestamp())


def _entry(symbol: str, **fields) -> CalendarEntry:
    base = {
        "exchange": "IDX",
        "symbol": symbol,
        "name": f"PT {symbol} Tbk",
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


@pytest.fixture(autouse=True)
def reset_fakes():
    fakes.ENTRIES.clear()
    fakes.FAIL["calendar"] = False
    yield
    fakes.ENTRIES.clear()


class TestApplyAction:
    def test_style_switch_sets_the_style(self):
        state = PageState(dark=True)

        assert apply_action(state, "style", "long")
        assert state.style == "long"

    def test_unknown_style_is_ignored(self):
        state = PageState(dark=True)

        assert not apply_action(state, "style", "yolo")
        assert state.style == "short"

    def test_filter_clicks_toggle_the_filter(self):
        state = PageState(dark=True)

        apply_action(state, "filter", "payout")
        assert state.filters == {"payout"}
        apply_action(state, "filter", "payout")
        assert state.filters == frozenset()

    def test_unknown_filter_is_ignored(self):
        state = PageState(dark=True)

        assert not apply_action(state, "filter", "nonsense")
        assert state.filters == frozenset()

    def test_view_only_accepts_the_two_views(self):
        state = PageState(dark=True)

        assert apply_action(state, "view", "month")
        assert not apply_action(state, "view", "kanban")
        assert state.view == "month"

    def test_select_and_help(self):
        state = PageState(dark=True)

        apply_action(state, "select", "IDX:SIDO")
        apply_action(state, "help", "")

        assert state.selected == "IDX:SIDO"
        assert state.help is True

    def test_unknown_action_changes_nothing(self):
        assert not apply_action(PageState(dark=True), "delete", "everything")


class TestCalendarPage:
    async def test_lists_dividends_ranked_with_their_names(self):
        fakes.ENTRIES.extend([_entry("SIDO"), _entry("TSPC", payout=38.0)])
        async with simulate() as user:
            await user.open("/calendar")

            await user.should_see("Dividend hunter")
            await user.should_see("SIDO")
            await user.should_see("TSPC")

    async def test_explains_the_four_dates_in_the_guide(self):
        fakes.ENTRIES.append(_entry("SIDO"))
        async with simulate() as user:
            await user.open("/calendar")

            await user.should_see("How to use this page")

    async def test_shows_the_unavailable_message_when_the_scan_fails(self):
        fakes.FAIL["calendar"] = True
        async with simulate() as user:
            await user.open("/calendar")

            await user.should_see("Calendar unavailable")

    async def test_a_symbol_is_absent_when_the_calendar_has_no_dividends(self):
        async with simulate() as user:
            await user.open("/calendar")

            await user.should_not_see("SIDO")

    async def test_an_empty_calendar_still_renders_the_page(self):
        async with simulate() as user:
            await user.open("/calendar")

            await user.should_see("Dividend hunter")


def test_default_style_is_the_short_term_hunter():
    assert HuntStyle(PageState(dark=True).style) is HuntStyle.SHORT
