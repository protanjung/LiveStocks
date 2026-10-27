"""EPS and revenue actual-versus-estimate chart and table.
financial_options builds the ECharts bars and fin_table the per-period rows.
Revenue is abbreviated to T, B or M; EPS keeps two decimals.
"""

from html import escape

from livestocks.domain import Period
from livestocks.ui.chart import COLORS, MONO

_ESCAPE_JS = (
    "const esc = (s) => String(s).replace(/[&<>\"']/g, (ch) => "
    "({'&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;', \"'\": '&#39;'})[ch]);"
)
_COMPACT_JS = (
    "const c = (v) => { const a = Math.abs(v);"
    " return a >= 1e12 ? (v / 1e12).toFixed(2) + ' T' : a >= 1e9 ? (v / 1e9).toFixed(2) + ' B'"
    " : a >= 1e6 ? (v / 1e6).toFixed(2) + ' M' : v.toLocaleString('en-US', {maximumFractionDigits: 2}); };"
)


def compact(v: float | None, kind: str) -> str:
    """Format a value for EPS (two decimals) or revenue (abbreviated with T, B or M).
    Anything below a million prints as a whole number.
    None becomes an em dash.
    """
    if v is None:
        return "—"
    if kind == "eps":
        return f"{v:,.2f}"
    a = abs(v)
    for size, suffix in ((1e12, " T"), (1e9, " B"), (1e6, " M")):
        if a >= size:
            return f"{v / size:,.2f}{suffix}"
    return f"{v:,.0f}"


def short_label(label: str) -> str:
    """Shorten a fiscal period label: '2026-Q2' becomes 'Q2 26', years stay as they are.
    Keeps chart axes and table headers narrow.
    Used by both the chart and the table.
    """
    if "-Q" in label:
        year, q = label.split("-")
        return f"{q} {year[-2:]}"
    return label


# ---- table ----
def fin_table(periods: tuple[Period, ...], kind: str) -> str:
    """Return the scrollable table of reported, estimate and surprise per period.
    The first column stays frozen while the periods scroll sideways.
    Surprise is green for beats and red for misses.
    """
    head = "".join(f"<th class='r'>{escape(short_label(p.label))}</th>" for p in periods)
    reported = "".join(f"<td class='r num'>{compact(p.actual, kind)}</td>" for p in periods)
    estimate = "".join(f"<td class='r num'>{compact(p.estimate, kind)}</td>" for p in periods)

    def surprise(p: Period) -> str:
        s = p.surprise
        if s is None:
            return "<td class='r muted'>—</td>"
        return f"<td class='r num {'pos' if s >= 0 else 'neg'}'>{'+' if s >= 0 else '−'}{abs(s) * 100:.2f}%</td>"

    return (
        '<div class="tablewrap fin"><table class="fintable"><thead><tr><th>Metric</th>'
        f"{head}</tr></thead><tbody>"
        f"<tr><th>Reported</th>{reported}</tr><tr><th>Estimate</th>{estimate}</tr>"
        f"<tr><th>Surprise</th>{''.join(surprise(p) for p in periods)}</tr></tbody></table></div>"
    )


# ---- chart ----
def financial_options(periods: tuple[Period, ...], kind: str, dark: bool) -> dict:
    """Build the ECharts option dict for one EPS or revenue series.
    Reported and estimate bars sit side by side; future periods get a FORECAST area.
    kind picks the colour and number format, dark the palette.
    """
    col = COLORS[dark]
    labels = [short_label(p.label) for p in periods]
    reported_color = col["accent"] if kind == "eps" else ("#e8b04a" if dark else "#a96f0a")
    est_color = col["muted"]
    first_forecast = next((i for i, p in enumerate(periods) if not p.reported), None)

    estimate_series: dict = {
        "name": "Estimate",
        "type": "bar",
        "data": [p.estimate for p in periods],
        "barMaxWidth": 18,
        "itemStyle": {"color": est_color, "opacity": 0.45, "borderRadius": [3, 3, 0, 0]},
    }
    if first_forecast is not None:
        estimate_series["markArea"] = {
            "silent": True,
            "itemStyle": {"color": est_color, "opacity": 0.08},
            "label": {
                "show": True,
                "position": "insideBottomRight",
                "color": col["muted"],
                "fontSize": 10,
                "fontFamily": MONO,
                "distance": 6,
            },
            "data": [
                [{"xAxis": labels[first_forecast], "name": "FORECAST"}, {"xAxis": labels[-1]}]
            ],
        }
    return {
        "animation": False,
        "grid": {"left": 8, "right": 12, "top": 16, "bottom": 36, "containLabel": True},
        "legend": {
            "bottom": 0,
            "icon": "circle",
            "itemWidth": 8,
            "itemHeight": 8,
            "textStyle": {"color": col["muted"], "fontSize": 11},
            "data": [
                {"name": "Reported", "itemStyle": {"color": reported_color}},
                {"name": "Estimate", "itemStyle": {"color": est_color}},
            ],
        },
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "shadow", "shadowStyle": {"opacity": 0.08}},
            "backgroundColor": col["surface"],
            "borderColor": col["line"],
            "textStyle": {"color": col["fg"], "fontFamily": MONO, "fontSize": 12},
            ":formatter": """(ps) => {
                __COMPACT__
                const by = Object.fromEntries(ps.map(p => [p.seriesName, p.value]));
                const a = by['Reported'], e = by['Estimate'];
                const s = (a != null && e) ? ((a - e) / Math.abs(e) * 100) : null;
                const row = (k, v) => `<div>${k} <b style="float:right;margin-left:16px">${v == null ? '—' : c(v)}</b></div>`;
                return `<div style="opacity:.7;margin-bottom:4px">${esc(ps[0].axisValue)}</div>` + row('Reported', a) + row('Estimate', e)
                    + (s == null ? '' : `<div>Surprise <b style="float:right;margin-left:16px">${s >= 0 ? '+' : '−'}${Math.abs(s).toFixed(2)}%</b></div>`);
            }""".replace("__COMPACT__", _ESCAPE_JS + _COMPACT_JS),
        },
        "xAxis": {
            "type": "category",
            "data": labels,
            "axisTick": {"show": False},
            "axisLine": {"lineStyle": {"color": col["line"]}},
            "axisLabel": {"color": col["muted"], "fontSize": 10, "hideOverlap": True},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {
                "color": col["muted"],
                "fontSize": 10,
                "fontFamily": MONO,
                ":formatter": f"(v) => {{ {_COMPACT_JS} return c(v); }}",
            },
            "splitLine": {"lineStyle": {"color": col["line"], "type": "dashed"}},
        },
        "series": [
            {
                "name": "Reported",
                "type": "bar",
                "data": [p.actual for p in periods],
                "barMaxWidth": 18,
                "itemStyle": {"color": reported_color, "borderRadius": [3, 3, 0, 0]},
            },
            estimate_series,
        ],
    }
