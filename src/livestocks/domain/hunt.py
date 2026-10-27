"""Dividend-hunting rules: a 0-100 hunt score and a pass/warn/fail checklist for a calendar entry.
The thresholds follow the usual Indonesian dividend-hunting guide: yield, payout ratio, consistency,
cash flow, liquidity and the dividend trap. Pure functions, no I/O.
"""

import math
from dataclasses import dataclass
from enum import StrEnum

from livestocks.domain.models import CalendarEntry


class HuntStyle(StrEnum):
    """The two ways to hunt: SHORT buys before the Cum Date and sells around the Ex Date.
    LONG holds for the income and reinvests, so yield and consistency count for more.
    The value is a plain string so it can be kept in the page state and compared to it.
    """

    SHORT = "short"
    LONG = "long"


class CheckStatus(StrEnum):
    """The result of one checklist item: PASS meets the guide, WARN is borderline, FAIL does not.
    NA means the data needed for the check is missing, which is never counted as a pass.
    Values are plain strings, so they double as CSS class names.
    """

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    NA = "na"


@dataclass(frozen=True, slots=True)
class Check:
    """One line of the checklist: what was checked, how it came out, and the numbers behind it.
    detail is a short sentence such as 'Payout 131%, above the 90% limit'.
    The label names the factor, for example Payout ratio or Dividend trap.
    """

    label: str
    status: CheckStatus
    detail: str


# Weight of each factor in the score, per style.
# A missing factor is left out and the rest are re-weighted.
WEIGHTS: dict[HuntStyle, dict[str, float]] = {
    HuntStyle.SHORT: {
        "event": 30,
        "trap": 25,
        "liquidity": 15,
        "payout": 10,
        "streak": 10,
        "annual": 10,
    },
    HuntStyle.LONG: {
        "annual": 25,
        "streak": 25,
        "payout": 20,
        "coverage": 15,
        "trap": 5,
        "event": 5,
        "liquidity": 5,
    },
}
MIN_FACTORS = 3  # a score needs at least this many factors with data
LIQUID_TURNOVER = 1_000_000_000  # IDR traded per day that counts as liquid
THIN_TURNOVER = 200_000_000


def _payout_factor(payout: float | None) -> float | None:
    """Score a payout ratio: 30-70 % is ideal, over 90 % leaves the company no room to grow."""
    if payout is None:
        return None
    if 30 <= payout <= 70:
        return 1.0
    if payout < 30:
        return 0.7
    if payout <= 90:
        return 0.6
    return 0.3 if payout <= 100 else 0.0


def _liquidity_factor(turnover: float | None) -> float | None:
    """Score daily turnover on a log scale from 100 M IDR (0) to 5 B IDR (1)."""
    if turnover is None:
        return None
    if turnover <= 1e8:
        return 0.0
    return min(math.log10(turnover / 1e8) / math.log10(50), 1.0)


def _coverage_factor(coverage: float | None) -> float | None:
    """Score how many times cash flow covers the dividend: 1.5x or more is comfortable."""
    if coverage is None:
        return None
    return 1.0 if coverage >= 1.5 else 0.6 if coverage >= 1.0 else 0.2


def _trap_factor(entry: CalendarEntry) -> float | None:
    """Score trap risk from the stock's own Ex Date history: low is best, no history is unknown."""
    level = entry.trap.level if entry.trap else None
    return {"low": 1.0, "med": 0.5, "high": 0.0}.get(level or "")


def hunt_factors(entry: CalendarEntry) -> dict[str, float | None]:
    """Return each scoring factor of an entry as 0 to 1, or None when its data is missing.
    The factors: event yield, annual yield, payout ratio, streak, coverage, liquidity, trap risk.
    The score and the tests both read this, so the weights are the only thing a style changes.
    """
    ey = entry.event_yield
    return {
        "event": None if ey is None else min(ey / 6, 1.0),
        "annual": None if entry.yield_pct is None else min(entry.yield_pct / 10, 1.0),
        "payout": _payout_factor(entry.payout),
        "streak": None if entry.streak_years is None else min(entry.streak_years / 5, 1.0),
        "coverage": _coverage_factor(entry.coverage),
        "liquidity": _liquidity_factor(entry.turnover),
        "trap": _trap_factor(entry),
    }


def hunt_score(entry: CalendarEntry, style: HuntStyle = HuntStyle.SHORT) -> int | None:
    """Return a 0-100 score for how attractive a dividend is to hunt in the chosen style.
    Each factor is weighted for the style and the weights are re-scaled over the data that exists.
    Returns None when fewer than MIN_FACTORS factors have data, leaving a thin row unranked.
    """
    factors = hunt_factors(entry)
    weights = WEIGHTS[style]
    have = {k: v for k, v in factors.items() if v is not None and k in weights}
    if len(have) < MIN_FACTORS:
        return None
    total = sum(weights[k] for k in have)
    return round(100 * sum(weights[k] * v for k, v in have.items()) / total)


def hunt_checks(entry: CalendarEntry) -> list[Check]:
    """Return the guide's checklist: yield, payout, consistency, cash flow, liquidity and trap.
    Each item is a pass, a warning, a fail, or NA when the data is missing.
    Thresholds: yield above 4 %, payout 30-70 % (over 90 % fails), three years or more.
    """
    checks: list[Check] = []
    y = entry.yield_pct
    checks.append(
        Check("Yield", CheckStatus.NA, "No yield data")
        if y is None
        else Check(
            "Yield",
            CheckStatus.PASS if y >= 4 else CheckStatus.WARN,
            f"{y:.1f}% a year" + ("" if y >= 4 else ", below the 4% guide"),
        )
    )
    p = entry.payout
    if p is None:
        checks.append(Check("Payout ratio", CheckStatus.NA, "No payout data"))
    elif 30 <= p <= 70:
        checks.append(Check("Payout ratio", CheckStatus.PASS, f"{p:.0f}%, inside the 30-70% range"))
    elif p > 90:
        checks.append(Check("Payout ratio", CheckStatus.FAIL, f"{p:.0f}%, above the 90% limit"))
    else:
        checks.append(
            Check("Payout ratio", CheckStatus.WARN, f"{p:.0f}%, outside the 30-70% range")
        )
    s = entry.streak_years
    if s is None:
        checks.append(Check("Consistency", CheckStatus.NA, "No history data"))
    else:
        status = CheckStatus.PASS if s >= 3 else CheckStatus.WARN if s >= 1 else CheckStatus.FAIL
        checks.append(
            Check("Consistency", status, f"{s} year{'s' if s != 1 else ''} paying in a row")
        )
    c = entry.coverage
    if c is None:
        checks.append(Check("Cash flow", CheckStatus.NA, "No cash flow data"))
    else:
        checks.append(
            Check(
                "Cash flow",
                CheckStatus.PASS if c >= 1 else CheckStatus.WARN,
                f"Dividend covered {c:.1f}x by cash flow",
            )
        )
    t = entry.turnover
    if t is None:
        checks.append(Check("Liquidity", CheckStatus.NA, "No volume data"))
    else:
        status = (
            CheckStatus.PASS
            if t >= LIQUID_TURNOVER
            else CheckStatus.WARN
            if t >= THIN_TURNOVER
            else CheckStatus.FAIL
        )
        checks.append(Check("Liquidity", status, f"IDR {t / 1e9:.2f} B traded a day"))
    level = entry.trap.level if entry.trap else None
    if level is None:
        checks.append(Check("Dividend trap", CheckStatus.NA, "Not enough Ex Date history"))
    else:
        rate = entry.trap.trap_rate if entry.trap else None
        n = len(entry.trap.events) if entry.trap else 0
        hits = round((rate or 0) * n)
        status = {"low": CheckStatus.PASS, "med": CheckStatus.WARN, "high": CheckStatus.FAIL}[level]
        checks.append(
            Check("Dividend trap", status, f"The drop beat the dividend in {hits} of {n} Ex Dates")
        )
    return checks
