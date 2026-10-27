"""Seasonal chart: each calendar year's return by day, with the average across years.
seasonal_returns measures every day from the previous year-end close, and seasonal_options draws one line per year.
Days sit on a shared leap-year calendar so years line up; a year with no previous year-end close is dropped.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from livestocks.domain import PriceBar
from livestocks.ui.chart import COLORS

# Noon UTC keeps each slot on the same date in any timezone the browser shows the axis in.
_CALENDAR = [datetime(2000, 1, 1, 12, tzinfo=UTC) + timedelta(days=i) for i in range(366)]
DAY_KEYS = [(d.month, d.day) for d in _CALENDAR]
DAY_MS = [int(d.timestamp() * 1000) for d in _CALENDAR]


def _daily_closes(
    bars: Sequence[PriceBar],
) -> tuple[dict[int, dict[tuple[int, int], float]], dict[int, float]]:
    """Return each year's closes keyed by (month, day) in UTC, and each year's last close.
    Bars may arrive in any order; sorting first makes the latest bar of a day win.
    The year-end close is the last bar of that year, which is what the next year is measured from.
    """
    daily: dict[int, dict[tuple[int, int], float]] = {}
    year_end: dict[int, float] = {}
    for bar in sorted(bars, key=lambda b: b.ts):
        when = datetime.fromtimestamp(bar.ts, UTC)
        daily.setdefault(when.year, {})[(when.month, when.day)] = bar.close
        year_end[when.year] = bar.close
    return daily, year_end


def seasonal_returns(bars: Sequence[PriceBar]) -> dict[int, list[float | None]]:
    """Return each year's cumulative percent return for every calendar day, 366 slots per year.
    Each day is measured from the previous year's last close; weekends and holidays repeat the last close.
    Days before a year's first bar are None, and the latest year stops at its last bar.
    """
    daily, year_end = _daily_closes(bars)
    latest = max(daily, default=0)
    returns: dict[int, list[float | None]] = {}
    for year in sorted(daily):
        base = year_end.get(year - 1)
        if base is None:
            continue
        keys = daily[year]
        end = max(keys) if year == latest else (12, 31)
        row: list[float | None] = []
        close: float | None = None
        for key in DAY_KEYS:
            close = keys.get(key, close)
            row.append(None if close is None or key > end else (close / base - 1) * 100)
        returns[year] = row
    return returns


def seasonal_average(by_year: dict[int, list[float | None]]) -> list[float | None]:
    """Return the mean percent return for each day across the years that have a value for it.
    A day where no year has data stays None, so a partial current year only averages what exists.
    Years are not weighted, so each contributes equally to its day.
    """
    if not by_year:
        return [None] * len(DAY_KEYS)
    average: list[float | None] = []
    for column in zip(*by_year.values(), strict=True):
        values = [v for v in column if v is not None]
        average.append(sum(values) / len(values) if values else None)
    return average


def _points(row: Sequence[float | None]) -> list[list[float]]:
    """Pair each day's timestamp with its value, leaving out days without one.
    The result is the [timestamp, value] shape that a time axis expects.
    Values are rounded to two decimals to keep the chart payload small.
    """
    return [[DAY_MS[i], round(v, 2)] for i, v in enumerate(row) if v is not None]


def seasonal_options(bars: Sequence[PriceBar], dark: bool) -> dict:
    """Build the ECharts option dict: one line per year over the calendar, plus a bold Average line.
    Days sit on a time axis labelled by month. The latest year is drawn in the accent colour and older years fade.
    dark picks the palette; the tooltip lists every year that has a value for the hovered day.
    """
    col = COLORS[dark]
    by_year = seasonal_returns(bars)
    years = sorted(by_year)
    latest = years[-1] if years else None
    series: list[dict] = []
    for year in years:
        is_latest = year == latest
        series.append(
            {
                "name": str(year),
                "type": "line",
                "data": _points(by_year[year]),
                "showSymbol": False,
                "lineStyle": {"width": 2 if is_latest else 1, "opacity": 1 if is_latest else 0.2},
                "itemStyle": {"color": col["accent"] if is_latest else col["muted"]},
            }
        )
    series.append(
        {
            "name": "Average",
            "type": "line",
            "data": _points(seasonal_average(by_year)),
            "showSymbol": False,
            "z": 5,
            "lineStyle": {"width": 3},
            "itemStyle": {"color": col["fg"]},
            "markLine": {
                "silent": True,
                "symbol": "none",
                "label": {"show": False},
                "lineStyle": {"color": col["muted"], "opacity": 0.5},
                "data": [{"yAxis": 0}],
            },
        }
    )
    return {
        "animation": False,
        "aria": {"enabled": True},
        "grid": {"left": 8, "right": 12, "top": 16, "bottom": 12, "containLabel": True},
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": col["surface"],
            "borderColor": col["line"],
            "textStyle": {"color": col["fg"], "fontSize": 12},
            ":formatter": """(ps) => {
                const day = new Date(ps[0].value[0]).toLocaleDateString('en-GB',
                    {day: 'numeric', month: 'short', timeZone: 'UTC'});
                const rows = ps.filter(p => p.value[1] != null).map(p =>
                    `<div>${p.seriesName} <b style="float:right;margin-left:16px">`
                    + `${p.value[1] >= 0 ? '+' : '−'}${Math.abs(p.value[1]).toFixed(2)}%</b></div>`);
                return `<div style="opacity:.7;margin-bottom:4px">${day}</div>` + rows.join('');
            }""",
        },
        "xAxis": {
            "type": "time",
            "min": DAY_MS[0],
            "max": DAY_MS[-1],
            "axisTick": {"show": False},
            "axisLine": {"lineStyle": {"color": col["line"]}},
            "axisLabel": {"color": col["muted"], "fontSize": 10, "formatter": "{MMM}"},
            "splitLine": {"show": False},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {
                "color": col["muted"],
                "fontSize": 10,
                ":formatter": "(v) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(0) + '%'",
            },
            "splitLine": {"lineStyle": {"color": col["line"], "type": "dashed"}},
        },
        "series": series,
    }
