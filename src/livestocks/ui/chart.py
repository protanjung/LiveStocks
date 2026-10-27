"""Price + forecast cone chart, modelled on TradingView's forecast page.

History is the daily close line; from the latest close a cone fans out one year ahead to the low / average / high
analyst targets, with a flat line at the current price and labelled pills at the right edge.
"""

from collections.abc import Sequence

from livestocks.domain import Forecast, PriceBar
from livestocks.ui.components import price_fmt

YEAR_MS = 365 * 86400 * 1000
MONO = "IBM Plex Mono, monospace"

COLORS = {
    True: {
        "fg": "#e6ebf5",
        "muted": "#8a97b2",
        "line": "#243049",
        "accent": "#6ea0ff",
        "surface": "#131a28",
        "pos": "#34c38f",
        "neg": "#f0616d",
    },
    False: {
        "fg": "#121a2b",
        "muted": "#5a6781",
        "line": "#dfe4ee",
        "accent": "#2e62d9",
        "surface": "#ffffff",
        "pos": "#0f8f63",
        "neg": "#c8323f",
    },
}

_TOOLTIP = """(ps) => {
    const p = ps.find(x => x.seriesName === 'Price');
    if (!p) return '';
    const d = new Date(p.value[0]), v = p.value[1];
    const f = v >= 100 ? Math.round(v).toLocaleString('en-US') : v.toFixed(2);
    return `<div style="opacity:.7">${d.toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric'})}</div><b>${f}</b>`;
}"""


def _pill(label: str, value: float, color: str, col: dict, position: str = "top") -> dict:
    """Label config: a coloured label box joined to an outlined value box, right-aligned to its point."""
    return {
        "show": True,
        "position": position,
        "align": "right",
        "distance": 5,
        # phones are too narrow for "Max +79.7%": drop the percentage there
        ":formatter": (
            f"() => '{{a|' + (innerWidth < 600 ? '{label.split(' ')[0]}' : '{label}')"
            f" + '}}{{b|{price_fmt(value)}}}'"
        ),
        "rich": {
            "a": {
                "backgroundColor": color,
                "color": "#fff",
                "padding": [5, 7],
                "borderRadius": [4, 0, 0, 4],
                "fontSize": 11,
                "fontFamily": MONO,
            },
            "b": {
                "backgroundColor": col["surface"],
                "color": color,
                "padding": [4, 7],
                "borderRadius": [0, 4, 4, 0],
                "borderColor": color,
                "borderWidth": 1,
                "fontSize": 11,
                "fontWeight": 600,
                "fontFamily": MONO,
            },
        },
    }


def _pill_series(
    label: str, t1: int, value: float, color: str, col: dict, position: str = "top"
) -> dict:
    """Invisible one-point series that carries a pill label above every line.
    A label drawn by a line series sits at that line's z level, so another line could cross it.
    Giving the pills their own series with a high z keeps them on top, and they avoid each other.
    """
    return {
        "name": f"{label} pill",
        "type": "scatter",
        "silent": True,
        "symbolSize": 0,
        "z": 10,
        "data": [[t1, value]],
        "label": _pill(label, value, color, col, position),
        "labelLayout": {"moveOverlap": "shiftY"},
    }


def _target_line(
    name: str,
    t0: int,
    t1: int,
    price: float,
    target: float,
    color: str,
    col: dict,
    position: str = "top",
) -> list[dict]:
    pct = (target / price - 1) * 100 if price else 0.0
    line = {
        "name": name,
        "type": "line",
        "silent": True,
        "showSymbol": False,
        "z": 3,
        "data": [[t0, price], [t1, target]],
        "lineStyle": {"color": color, "width": 1.5, "type": [2, 3]},
    }
    return [line, _pill_series(f"{name} {pct:+.1f}%", t1, target, color, col, position)]


def forecast_options(bars: Sequence[PriceBar], f: Forecast, dark: bool, now_ms: int) -> dict:
    """Build the ECharts option dict for the price line and the forecast cone.
    bars are the visible daily closes; the cone fans out one year from the last bar.
    dark selects the palette and now_ms is the anchor when there are no bars.
    """
    col = COLORS[dark]
    data = [[b.ts * 1000, b.close] for b in bars]
    price = f.price if f.price is not None else (data[-1][1] if data else None)
    t0 = data[-1][0] if data else now_ms
    t1 = t0 + YEAR_MS

    series: list[dict] = [
        {
            "name": "Price",
            "type": "line",
            "data": data,
            "showSymbol": False,
            "z": 4,
            "lineStyle": {"color": col["accent"], "width": 2},
            "areaStyle": {
                "color": {
                    "type": "linear",
                    "x": 0,
                    "y": 0,
                    "x2": 0,
                    "y2": 1,
                    "colorStops": [
                        {"offset": 0, "color": col["accent"] + "40"},
                        {"offset": 1, "color": col["accent"] + "00"},
                    ],
                }
            },
        }
    ]
    if price is not None:
        series.append(
            {
                "name": "Current",
                "type": "line",
                "silent": True,
                "showSymbol": False,
                "z": 4,
                "data": [[t0, price], [t1, price]],
                "lineStyle": {"color": col["accent"], "width": 2},
            }
        )
        # Current sits above its line unless a target hangs below it; then it goes under the line instead,
        # so it never lands on top of the nearest target pill.
        targets = (f.pt_low, f.pt_avg, f.pt_high)
        any_below = any(t is not None and t < price for t in targets)
        series.append(
            _pill_series("Current", t1, price, col["accent"], col, "top" if any_below else "bottom")
        )
        if f.pt_low is not None and f.pt_high is not None:
            cone = col["pos"] if (f.pt_avg or price) >= price else col["neg"]
            series += [
                # invisible base up to the low target, then the stacked low-to-high band
                {
                    "name": "Cone base",
                    "type": "line",
                    "stack": "cone",
                    "silent": True,
                    "showSymbol": False,
                    "data": [[t0, price], [t1, f.pt_low]],
                    "lineStyle": {"opacity": 0},
                    "z": 1,
                },
                {
                    "name": "Cone",
                    "type": "line",
                    "stack": "cone",
                    "silent": True,
                    "showSymbol": False,
                    "data": [[t0, 0], [t1, f.pt_high - f.pt_low]],
                    "lineStyle": {"opacity": 0},
                    "areaStyle": {"color": cone, "opacity": 0.14},
                    "z": 1,
                },
            ]
        for name, target in (("Max", f.pt_high), ("Avg", f.pt_avg), ("Min", f.pt_low)):
            if target is not None:
                # labels sit above their line's end; a target below the current price hangs below it instead
                series += _target_line(
                    name,
                    t0,
                    t1,
                    price,
                    target,
                    col["pos"] if target >= price else col["neg"],
                    col,
                    "top" if target >= price else "bottom",
                )

    return {
        "animation": False,
        "grid": {"left": 8, "right": 14, "top": 28, "bottom": 8, "containLabel": True},
        "tooltip": {
            "trigger": "axis",
            "backgroundColor": col["surface"],
            "borderColor": col["line"],
            "textStyle": {"color": col["fg"], "fontFamily": MONO, "fontSize": 12},
            "axisPointer": {"type": "line", "lineStyle": {"color": col["muted"], "type": "dashed"}},
            ":formatter": _TOOLTIP,
        },
        "xAxis": {
            "type": "time",
            "max": t1,
            "axisLine": {"lineStyle": {"color": col["line"]}},
            "axisLabel": {"color": col["muted"], "fontSize": 10, "hideOverlap": True},
            "splitLine": {"show": False},
        },
        "yAxis": {
            "type": "value",
            "scale": True,
            "boundaryGap": ["4%", "8%"],
            "axisLabel": {"color": col["muted"], "fontSize": 10, "fontFamily": MONO},
            "splitLine": {"lineStyle": {"color": col["line"], "type": "dashed"}},
        },
        "series": series,
    }
