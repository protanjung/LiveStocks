"""Seasonal chart: each calendar year's return by month, with the average across years.
seasonal_returns measures every month from the previous December close, and seasonal_options draws one line per year.
Years without a prior December close are dropped, so a partial first year never skews the average.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from livestocks.domain import PriceBar
from livestocks.ui.chart import COLORS

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _month_ends(bars: Sequence[PriceBar]) -> dict[tuple[int, int], float]:
    """Return the last close of each (year, month) in UTC, so a month keeps its final bar.
    Bars may arrive in any order; the latest timestamp per month wins.
    """
    ends: dict[tuple[int, int], float] = {}
    for bar in sorted(bars, key=lambda b: b.ts):
        when = datetime.fromtimestamp(bar.ts, UTC)
        ends[(when.year, when.month)] = bar.close
    return ends


def seasonal_returns(bars: Sequence[PriceBar]) -> dict[int, list[float | None]]:
    """Return each year's cumulative percent return per month, keyed by year, twelve entries each.
    Each month is measured from the previous December close; months without a bar are None.
    A year with no previous December close is left out entirely.
    """
    ends = _month_ends(bars)
    returns: dict[int, list[float | None]] = {}
    for year in sorted({y for y, _ in ends}):
        base = ends.get((year - 1, 12))
        if base is None:
            continue
        returns[year] = [
            None if (close := ends.get((year, m))) is None else (close / base - 1) * 100
            for m in range(1, 13)
        ]
    return returns


def seasonal_average(by_year: dict[int, list[float | None]]) -> list[float | None]:
    """Return the mean percent return for each month across the years that have a value for it.
    A month where no year has data stays None, so a partial current year only averages what exists.
    Years are not weighted, so each contributes equally to its month.
    """
    if not by_year:
        return [None] * 12
    average: list[float | None] = []
    for column in zip(*by_year.values(), strict=True):
        values = [v for v in column if v is not None]
        average.append(sum(values) / len(values) if values else None)
    return average


def seasonal_options(bars: Sequence[PriceBar], dark: bool) -> dict:
    """Build the ECharts option dict: one line per year over Jan to Dec, plus a bold Average line.
    The latest year is drawn in the accent colour and older years fade into the muted tone.
    dark picks the palette; the tooltip lists every year that has a value for the hovered month.
    """
    col = COLORS[dark]
    by_year = seasonal_returns(bars)
    years = sorted(by_year)
    series: list[dict] = []
    for year in years:
        is_latest = year == years[-1]
        series.append(
            {
                "name": str(year),
                "type": "line",
                "data": [None if v is None else round(v, 2) for v in by_year[year]],
                "showSymbol": False,
                "connectNulls": False,
                "lineStyle": {"width": 2 if is_latest else 1, "opacity": 1 if is_latest else 0.35},
                "itemStyle": {"color": col["accent"] if is_latest else col["muted"]},
            }
        )
    series.append(
        {
            "name": "Average",
            "type": "line",
            "data": [None if v is None else round(v, 2) for v in seasonal_average(by_year)],
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
        "grid": {"left": 8, "right": 12, "top": 16, "bottom": 12, "containLabel": True},
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": col["surface"],
            "borderColor": col["line"],
            "textStyle": {"color": col["fg"], "fontSize": 12},
            ":formatter": """(ps) => {
                const rows = ps.filter(p => p.value != null).map(p =>
                    `<div>${p.seriesName} <b style="float:right;margin-left:16px">`
                    + `${p.value >= 0 ? '+' : '−'}${Math.abs(p.value).toFixed(2)}%</b></div>`);
                return `<div style="opacity:.7;margin-bottom:4px">${ps[0].axisValue}</div>` + rows.join('');
            }""",
        },
        "xAxis": {
            "type": "category",
            "data": list(MONTHS),
            "boundaryGap": False,
            "axisTick": {"show": False},
            "axisLine": {"lineStyle": {"color": col["line"]}},
            "axisLabel": {"color": col["muted"], "fontSize": 10},
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
