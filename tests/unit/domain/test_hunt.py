import pytest

from livestocks.domain import (
    CalendarEntry,
    CalendarKind,
    CheckStatus,
    ExDateEvent,
    HuntStyle,
    TrapStats,
    hunt_checks,
    hunt_score,
)


def _entry(**fields) -> CalendarEntry:
    base = {
        "exchange": "IDX",
        "symbol": "SIDO",
        "name": "PT Sido",
        "ex_date": 1,
        "pay_date": 2,
        "amount": 10.0,
        "yield_pct": 10.9,
        "kind": CalendarKind.UPCOMING,
        "price": 316.0,
        "avg_volume": 26_500_000.0,
        "payout": 76.0,
        "streak_years": 13,
        "coverage": 1.1,
    }
    base.update(fields)
    return CalendarEntry(**base)


def _event(drop: float, dividend: float = 10.0) -> ExDateEvent:
    return ExDateEvent(
        ex_date=1, dividend=dividend, cum_close=500.0, ex_close=500.0 - drop, recover_days=2
    )


def _trap(drops: list[float]) -> TrapStats:
    return TrapStats(tuple(_event(d) for d in drops))


class TestExDateEvent:
    def test_drop_larger_than_dividend_is_a_trap(self):
        assert _event(drop=15).is_trap

    def test_drop_smaller_than_dividend_is_not_a_trap(self):
        assert not _event(drop=5).is_trap

    def test_price_rise_on_ex_date_is_a_negative_drop(self):
        assert _event(drop=-5).drop_pct == pytest.approx(-1.0)


class TestTrapStats:
    def test_level_needs_three_events(self):
        assert _trap([1, 1]).level is None

    def test_no_traps_is_low(self):
        assert _trap([1, 2, 3, 4, 5, 6]).level == "low"

    def test_two_of_six_traps_is_med(self):
        assert _trap([15, 15, 1, 1, 1, 1]).level == "med"

    def test_most_events_trapping_is_high(self):
        assert _trap([15, 15, 15, 1, 1, 1]).level == "high"

    def test_medians_summarise_the_events(self):
        stats = _trap([5, 10, 15])

        assert stats.median_drop_pct == pytest.approx(2.0)
        assert stats.median_dividend_pct == pytest.approx(2.0)

    def test_no_events_gives_no_summary(self):
        stats = TrapStats(())

        assert stats.trap_rate is None
        assert stats.median_drop_pct is None


class TestCalendarEntryDerived:
    def test_event_yield_is_amount_over_price(self):
        assert _entry().event_yield == pytest.approx(10 / 316 * 100)

    def test_event_yield_needs_a_price(self):
        assert _entry(price=None).event_yield is None

    def test_turnover_is_volume_times_price(self):
        assert _entry().turnover == pytest.approx(26_500_000 * 316)


class TestHuntScore:
    def test_a_healthy_entry_scores_high(self):
        assert hunt_score(_entry(trap=_trap([1, 1, 1, 1, 1, 1]))) >= 70

    def test_a_trap_prone_entry_scores_lower_than_a_clean_one(self):
        clean = hunt_score(_entry(trap=_trap([1] * 6)))
        risky = hunt_score(_entry(trap=_trap([20] * 6)))

        assert risky < clean

    def test_style_changes_the_ranking_weights(self):
        high_yield_short_history = _entry(yield_pct=14.0, streak_years=1, payout=60.0)
        steady = _entry(yield_pct=5.0, streak_years=25, payout=50.0)

        short_gap = hunt_score(high_yield_short_history, HuntStyle.SHORT) - hunt_score(
            steady, HuntStyle.SHORT
        )
        long_gap = hunt_score(high_yield_short_history, HuntStyle.LONG) - hunt_score(
            steady, HuntStyle.LONG
        )

        assert long_gap < short_gap

    def test_too_little_data_gives_no_score(self):
        bare = _entry(
            price=None,
            avg_volume=None,
            payout=None,
            streak_years=None,
            coverage=None,
            yield_pct=None,
        )

        assert hunt_score(bare) is None

    def test_missing_factors_do_not_count_as_zero(self):
        assert hunt_score(_entry(coverage=None)) is not None

    def test_score_stays_inside_zero_to_hundred(self):
        score = hunt_score(_entry(payout=500.0, yield_pct=500.0))

        assert 0 <= score <= 100


class TestHuntChecks:
    def _by_label(self, entry: CalendarEntry) -> dict:
        return {c.label: c for c in hunt_checks(entry)}

    def test_payout_over_ninety_fails(self):
        assert self._by_label(_entry(payout=131.0))["Payout ratio"].status is CheckStatus.FAIL

    def test_payout_inside_the_range_passes(self):
        assert self._by_label(_entry(payout=50.0))["Payout ratio"].status is CheckStatus.PASS

    def test_low_payout_is_only_a_warning(self):
        assert self._by_label(_entry(payout=10.0))["Payout ratio"].status is CheckStatus.WARN

    def test_streak_of_three_years_passes(self):
        assert self._by_label(_entry(streak_years=3))["Consistency"].status is CheckStatus.PASS

    def test_no_streak_fails(self):
        assert self._by_label(_entry(streak_years=0))["Consistency"].status is CheckStatus.FAIL

    def test_missing_data_is_na_not_a_pass(self):
        checks = self._by_label(_entry(payout=None, coverage=None))

        assert checks["Payout ratio"].status is CheckStatus.NA
        assert checks["Cash flow"].status is CheckStatus.NA

    def test_trap_check_reports_how_many_events_beat_the_dividend(self):
        check = self._by_label(_entry(trap=_trap([15, 15, 1, 1, 1, 1])))["Dividend trap"]

        assert check.status is CheckStatus.WARN
        assert "2 of 6" in check.detail

    def test_thin_liquidity_fails(self):
        assert self._by_label(_entry(avg_volume=10_000.0))["Liquidity"].status is CheckStatus.FAIL
