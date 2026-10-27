"""Pure HTML builders for dashboard widgets.
Class names come from ui/static/app.css and every dynamic string is escaped here.
No function in this module performs I/O or touches NiceGUI.
"""

import math
import time
from collections.abc import Callable
from datetime import datetime
from html import escape
from typing import Any

from livestocks.domain import Forecast, TrackedTicker, rating_label


# ---- formatting ----
def fmt(v: float | None, d: int = 0) -> str:
    """Format a number with thousands separators and d decimals.
    None and non-finite values become an em dash so tables never show None, nan or inf.
    Used for counts and other plain numbers.
    """
    if v is None or not math.isfinite(v):
        return "—"
    return f"{v:,.{d}f}"


def price_fmt(v: float | None) -> str:
    """Format a price: whole numbers from 1,000 up, two decimals below if fractional.
    So IDX prices read 2,310 while a US price reads 333.63.
    None becomes an em dash.
    """
    if v is None or not math.isfinite(v):
        return "—"
    return fmt(v, 2 if abs(v) < 1000 and v != int(v) else 0)


CURRENCY = "IDR"  # display currency for amounts; prices are quoted in it on IDX


def pct(v: float) -> str:
    """Format a fraction as a signed percentage with two decimals.
    Negative values use a true minus sign (-4.2%), positive ones a plus sign.
    Pair it with arrow() to build the up and down chips.
    """
    return f"{'+' if v >= 0 else '−'}{abs(v) * 100:.2f}%"


def arrow(v: float) -> str:
    """Return an up triangle for values of zero or more, otherwise a down triangle.
    Shape as well as colour tells gains from losses, which helps colour-blind users.
    Used in chips, price changes and the upside ranking.
    """
    return "▲" if v >= 0 else "▼"


def ago(ts: int | None, now: int | None = None) -> str:
    """Format a past unix timestamp as a relative time such as '4 min ago'.
    Under a minute reads 'just now'; None gives a dash.
    now overrides the clock for tests.
    """
    if ts is None:
        return "—"
    clock = now if now is not None else int(time.time())
    s = max(0, clock - ts)
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    return f"{s // 86400} d ago"


def duration(seconds: int | None) -> str:
    """Format a number of seconds as '3h 05m', '<1m' or 'now'.
    None gives a dash.
    Used for the refresh countdown in the header and the details card.
    """
    if seconds is None:
        return "—"
    if seconds <= 0:
        return "now"
    if seconds < 60:
        return "<1m"
    h, m = divmod(seconds // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def interval_text(seconds: int) -> str:
    """Describe a refresh interval in whole hours, as 'hour' or '6 hours'. Never less than one hour.
    Used in page footers, so the grammar matches the number.
    Intervals are rounded to whole hours, so 5400 seconds reads as two hours.
    """
    hours = max(1, round(seconds / 3600))
    return "hour" if hours == 1 else f"{hours} hours"


def date_short(ts: int | None, year: bool = True) -> str:
    """Format a unix timestamp as '29 Oct 2026', optionally without the year.
    None or zero gives a dash.
    Used for next-earnings and all-time-high dates.
    """
    if not ts:
        return "—"
    try:
        d = datetime.fromtimestamp(ts)
    except (OverflowError, OSError, ValueError):
        return "—"
    return f"{d.day} {d:%b %Y}" if year else f"{d.day} {d:%b}"


# ---- small pieces ----
def rate_pill(mark: float | None) -> str:
    """Return the coloured rating pill HTML for a consensus score.
    A missing score renders a dash instead of a pill.
    The tone decides the colour class.
    """
    label, tone = rating_label(mark)
    if tone == "none":
        return '<span class="muted">—</span>'
    return f'<span class="rate {tone}"><i></i>{label}</span>'


def upside_chip(up: float | None) -> str:
    """Return the green or red chip showing upside to the average target.
    A missing value renders a dash.
    Includes an arrow so the meaning does not depend on colour alone.
    """
    if up is None:
        return '<span class="muted">—</span>'
    return f'<span class="chip {"pos" if up >= 0 else "neg"}">{arrow(up)} {pct(up)}</span>'


def change_line(change_pct: float | None) -> str:
    """Return the small daily-change line shown under a price.
    Empty when the change is unknown.
    Green with an up arrow for gains, red with a down arrow for losses.
    """
    if change_pct is None:
        return ""
    return f'<div class="chg {"pos" if change_pct >= 0 else "neg"}">{arrow(change_pct)} {abs(change_pct):.2f}%</div>'


def range_bar(f: Forecast) -> str:
    """Return the inline low-to-high target bar with average tick and price dot.
    All three markers share one scale, padded slightly at both ends.
    Renders a dash when targets or price are missing.
    """
    if f.pt_low is None or f.pt_high is None or f.price is None:
        return '<span class="muted">—</span>'
    lo, hi = min(f.pt_low, f.price), max(f.pt_high, f.price)
    pad = (hi - lo) * 0.04 or 1
    a, b = lo - pad, hi + pad

    def pos(x: float) -> float:
        return (x - a) / (b - a) * 100

    avg = f'<div class="avg" style="left:{pos(f.pt_avg):.2f}%"></div>' if f.pt_avg else ""
    label = (
        f"Target range {price_fmt(f.pt_low)} to {price_fmt(f.pt_high)}, price {price_fmt(f.price)}"
    )
    return (
        f'<div class="range" role="img" aria-label="{label}"><div class="track"></div>'
        f'<div class="fill" style="left:{pos(f.pt_low):.2f}%;width:{pos(f.pt_high) - pos(f.pt_low):.2f}%"></div>'
        f'{avg}<div class="px" style="left:{pos(f.price):.2f}%"></div>'
        f'<span class="lo">{price_fmt(f.pt_low)}</span><span class="hi">{price_fmt(f.pt_high)}</span></div>'
    )


def ticker_cell(r: TrackedTicker) -> str:
    """Return the ticker column cell: exchange badge, a link to the symbol and the company name.
    The symbol is a real link so keyboard and middle-click users can open the detail page.
    All text is HTML-escaped.
    """
    href = escape(f"/t/{r.exchange}/{r.symbol}", quote=True)
    return (
        f'<div class="tk"><div class="badge-ex">{escape(r.exchange)}</div>'
        f'<div><b><a href="{href}">{escape(r.symbol)}</a></b>'
        f'<span class="nm">{escape(r.name or "—")}</span></div></div>'
    )


SORT_KEYS = ("ticker", "price", "up", "rating", "n")
# Columns after the ticker cell: price, avg target, upside, range, rating, analysts, updated, actions.
_VALUE_COLUMNS = 6


def sort_tickers(rows: list[TrackedTicker], key: str, direction: int) -> list[TrackedTicker]:
    """Return rows ordered by one of SORT_KEYS, with tickers that have no forecast last.
    direction is 1 for ascending and -1 for descending; unknown keys raise KeyError.
    Tickers without a forecast keep their input order after the ranked ones.
    """
    keys: dict[str, Callable[[TrackedTicker], Any]] = {
        "ticker": lambda r: r.symbol,
        "price": lambda r: r.forecast.price or 0 if r.forecast else 0,
        "up": lambda r: r.upside if r.upside is not None else -1e9,
        "rating": lambda r: r.forecast.rating_mark if r.forecast and r.forecast.rating_mark else 99,
        "n": lambda r: (r.forecast.n_analysts or 0) if r.forecast else 0,
    }
    ok = [r for r in rows if r.forecast]
    rest = [r for r in rows if not r.forecast]
    return sorted(ok, key=keys[key], reverse=direction < 0) + rest


def _head(label: str, key: str, sort_key: str, sort_dir: int, right: bool = False) -> str:
    """Return a sortable column header: a real button, with aria-sort on the active column."""
    cls = ' class="r"' if right else ""
    if key != sort_key:
        return (
            f'<th scope="col"{cls}><button type="button" data-act="sort" data-key="{key}">'
            f"{escape(label)}</button></th>"
        )
    up = sort_dir > 0
    marker = "↑" if up else "↓"
    order = "ascending" if up else "descending"
    return (
        f'<th scope="col"{cls} aria-sort="{order}"><button type="button" data-act="sort" '
        f'data-key="{key}">{escape(label)}<span aria-hidden="true"> {marker}</span></button></th>'
    )


def _action_buttons(r: TrackedTicker) -> str:
    """Return the retry and remove buttons for one row, named after the symbol they act on."""
    key = escape(r.key, quote=True)
    sym = escape(r.symbol)
    retry = (
        f'<button type="button" class="act retry" data-act="retry" data-key="{key}" '
        f'aria-label="Retry {sym}" title="Retry">↻</button>'
        if r.status in ("error", "failed")
        else ""
    )
    remove = (
        f'<button type="button" class="act" data-act="remove" data-key="{key}" '
        f'aria-label="Remove {sym}" title="Remove">✕</button>'
    )
    return retry + remove


def _row(r: TrackedTicker, busy: bool, now: int) -> str:
    """Return one table row: the ticker link, then values, or a single message for missing forecasts.
    The whole row carries data-href so a click anywhere on it opens the detail page.
    Failed and failing tickers show their error; pending ones show a fetching note.
    """
    f = r.forecast
    href = escape(f"/t/{r.exchange}/{r.symbol}", quote=True)
    cells = [f"<td>{ticker_cell(r)}</td>"]
    if f is None:
        if r.status == "failed":
            msg = (
                f'<span class="err">⚠ {escape(r.last_error or "failed")} · '
                f"gave up after {r.fail_count} tries</span>"
            )
        elif r.status == "error":
            msg = (
                f'<span class="err">⚠ {escape(r.last_error or "error")} · '
                f"retry {r.fail_count}</span>"
            )
        else:
            msg = '<span class="muted"><span class="spin"></span>Fetching first forecast…</span>'
        cells.append(f'<td colspan="{_VALUE_COLUMNS + 1}">{msg}</td>')
    else:
        avg = price_fmt(f.pt_avg) if f.pt_avg else "—"
        n = str(f.n_analysts if f.n_analysts is not None else "—")
        cells.append(
            f'<td class="r"><div class="num">{price_fmt(f.price)}</div>{change_line(f.change_pct)}</td>'
            f'<td class="r num">{avg}</td>'
            f'<td class="r">{upside_chip(r.upside)}</td>'
            f"<td>{range_bar(f)}</td>"
            f"<td>{rate_pill(f.rating_mark)}</td>"
            f'<td class="r num">{n}</td>'
        )
    updated = (
        '<span class="spin"></span>fetching'
        if busy and f
        else ago(r.fetched_at or r.last_fetch, now)
    )
    cells.append(f'<td class="muted">{updated}</td>')
    cells.append(f'<td class="r">{_action_buttons(r)}</td>')
    return f'<tr data-href="{href}">{"".join(cells)}</tr>'


def forecast_table(
    rows: list[TrackedTicker],
    sort_key: str,
    sort_dir: int,
    busy: frozenset[str] | set[str],
    now: int,
) -> str:
    """Return the dashboard table as one HTML string, rows in the requested sort order.
    Headers and row actions carry data-act attributes, and the page handles clicks on them in one place.
    busy holds the EXCHANGE:SYMBOL keys being crawled now; now is unix seconds for the updated column.
    """
    heads = "".join(
        [
            _head("Ticker", "ticker", sort_key, sort_dir),
            _head("Price", "price", sort_key, sort_dir, right=True),
            '<th scope="col" class="r">Avg target</th>',
            _head("Upside", "up", sort_key, sort_dir, right=True),
            '<th scope="col">Target range</th>',
            _head("Rating", "rating", sort_key, sort_dir),
            _head("Analysts", "n", sort_key, sort_dir, right=True),
            '<th scope="col">Updated</th>',
            '<th scope="col"><span class="visually-hidden">Actions</span></th>',
        ]
    )
    body = "".join(_row(r, r.key in busy, now) for r in sort_tickers(rows, sort_key, sort_dir))
    return f"<table><thead><tr>{heads}</tr></thead><tbody>{body}</tbody></table>"


# ---- dashboard sections ----
def kpi_strip(rows: list[TrackedTicker]) -> str:
    """Return the four summary cards shown above the table.
    They show tracked count, average upside, share rated buy and next earnings.
    Works with any mix of pending, failed and healthy tickers, including none.
    """
    ok = [r for r in rows if r.status == "ok" and r.upside is not None and r.forecast is not None]
    pending = sum(r.status == "pending" for r in rows)
    failed = sum(r.status in ("error", "failed") for r in rows)

    avg_up = sum(r.upside or 0.0 for r in ok) / len(ok) if ok else None
    if avg_up is None:
        up_html = '<div class="value">—</div>'
    else:
        up_html = f'<div class="value {"pos" if avg_up >= 0 else "neg"}">{arrow(avg_up)} {pct(avg_up)}</div>'

    marks = [
        r.forecast.rating_mark for r in ok if r.forecast and r.forecast.rating_mark is not None
    ]
    rated = marks
    bull = sum(mark < 2.5 for mark in marks)
    bull_html = f"{round(bull / len(rated) * 100)}%" if rated else "—"
    bull_note = f"{bull} of {len(rated)} tickers" if rated else "No ratings yet"

    now = int(time.time())
    upcoming = sorted(
        (
            (r.forecast.next_earnings, r)
            for r in ok
            if r.forecast and r.forecast.next_earnings and r.forecast.next_earnings >= now
        ),
        key=lambda pair: pair[0],
    )
    if upcoming:
        when, e = upcoming[0]
        earn_val, earn_note = (
            date_short(when, year=False),
            f"{escape(e.symbol)} · {escape(e.name or '')}",
        )
    else:
        earn_val, earn_note = "—", "No upcoming dates"

    return f"""<section class="kpis" aria-label="Summary">
    <div class="card kpi"><div class="label">Tracked tickers</div><div class="value">{len(rows)}</div>
      <div class="note">{len(ok)} with data · {pending} pending · {failed} failed</div></div>
    <div class="card kpi"><div class="label">Avg upside to target</div>{up_html}<div class="note">Mean of analyst average targets</div></div>
    <div class="card kpi"><div class="label">Rated buy or better</div><div class="value">{bull_html}</div><div class="note">{bull_note}</div></div>
    <div class="card kpi"><div class="label">Next earnings</div><div class="value">{earn_val}</div><div class="note">{earn_note}</div></div>
  </section>"""


def rank_card(rows: list[TrackedTicker]) -> str:
    """Return the card ranking tickers by upside to the average target.
    Positive bars grow right and negative bars left of a shared zero line.
    Empty when no ticker has an upside yet.
    """
    d = sorted(
        ((r.upside, r) for r in rows if r.upside is not None),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not d:
        return ""
    max_pos = max((up for up, _ in d if up > 0), default=0.001)
    max_neg = max((-up for up, _ in d if up < 0), default=0)
    zero = 22 if max_neg > 0 else 0
    out = []
    for up, r in d:
        w = up / max_pos * (100 - zero) if up >= 0 else -up / max_neg * zero
        left = zero if up >= 0 else zero - w
        color = "var(--pos)" if up >= 0 else "var(--neg)"
        out.append(
            f'<div class="rank-row"><span class="t">{escape(r.symbol)}</span>'
            f'<div class="bar" style="--zero:{zero}%"><i style="background:{color};left:{left:.2f}%;width:{w:.2f}%"></i></div>'
            f'<span class="v num {"pos" if up >= 0 else "neg"}">{arrow(up)} {pct(up)}</span></div>'
        )
    return (
        '<div class="card"><div class="card-head"><h2>Upside to average target</h2>'
        '<span class="sub">Ranked, highest first</span></div>'
        f'<div class="card-body rank">{"".join(out)}</div></div>'
    )


def dist_card(rows: list[TrackedTicker]) -> str:
    """Return the card counting how many tickers fall in each consensus bucket.
    Uses the same five buckets and cut-offs as the gauge, so Sell and Strong sell differ.
    Empty when no ticker has a rating.
    """
    marks = [
        r.forecast.rating_mark for r in rows if r.forecast and r.forecast.rating_mark is not None
    ]
    if not marks:
        return ""
    # same five buckets and cut-offs as rating_label / the gauge, so "Sell" and "Strong sell" stay apart
    cuts = [1.5, 2.5, 3.5, 4.5, float("inf")]
    counts = [0] * 5
    for m in marks:
        counts[next(i for i, c in enumerate(cuts) if m < c)] += 1
    groups = [(label, n, color) for (label, color), n in zip(GAUGE_ZONES, counts, strict=True)]
    bar = "".join(f'<i style="flex:{n};background:{c}"></i>' for _, n, c in groups if n)
    lst = "".join(
        f'<div><span><i style="background:{c}"></i>{label}</span><b class="num">{n}</b></div>'
        for label, n, c in groups
    )
    return (
        f'<div class="card"><div class="card-head"><h2>Consensus rating mix</h2><span class="sub">{len(marks)} tickers</span></div>'
        f'<div class="card-body"><div class="dist" role="img" aria-label="Rating mix">{bar}</div>'
        f'<div class="dist-list">{lst}</div></div></div>'
    )


def empty_state() -> str:
    """Return the card shown when no ticker is tracked yet.
    It explains that the crawler fetches a forecast right after one is added.
    It replaces the KPI strip, the table and the charts.
    """
    return """<section class="card empty">
    <svg width="56" height="56" viewBox="0 0 56 56" fill="none" aria-hidden="true"><rect x="2" y="2" width="52" height="52" rx="14" fill="var(--accent-soft)"/>
      <path d="M14 38l9-10 7 7 12-16" stroke="var(--accent)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
    <h3>No tickers tracked yet</h3>
    <p>Add a ticker in the box above. The crawler fetches its analyst forecast within seconds, then keeps it fresh in the background.</p></section>"""


# ---- detail ----
def big_range(f: Forecast) -> str:
    """Return the detail page's price-target scale with low, average, high and price pins.
    Also lists the upside to each target underneath.
    Shows a note instead when any of the four values is missing.
    """
    low, high, avg, price = f.pt_low, f.pt_high, f.pt_avg, f.price
    note = '<p class="muted">Price target range unavailable for this ticker.</p>'
    if low is None or high is None or avg is None or not price:
        return note
    lo, hi = min(low, price) * 0.97, max(high, price) * 1.03
    if hi <= lo:
        return note

    def p(x: float) -> float:
        return (x - lo) / (hi - lo) * 100

    def pin(x: float, label: str, cls: str = "", below: bool = False) -> str:
        return f'<div class="pin {cls} {"below" if below else ""}" style="left:{p(x):.2f}%"><b>{price_fmt(x)}</b>{label}</div>'

    return (
        f'<div class="big-range"><div class="track"></div>'
        f'<div class="fill" style="left:{p(low):.2f}%;width:{p(high) - p(low):.2f}%"></div>'
        f"{pin(low, 'Low')}{pin(avg, 'Average', 'avg')}{pin(high, 'High')}{pin(price, 'Price now', 'px', True)}</div>"
        f'<div class="legend" style="margin-top:18px;justify-content:space-between">'
        + "".join(
            f'<span>{label} <b class="num {"pos" if t / price - 1 >= 0 else "neg"}">'
            f"{arrow(t / price - 1)} {pct(t / price - 1)}</b></span>"
            for label, t in (
                ("Upside to low", low),
                ("Upside to average", avg),
                ("Upside to high", high),
            )
        )
        + "</div>"
    )


GAUGE_ZONES = [
    ("Strong buy", "var(--pos)"),
    ("Buy", "color-mix(in srgb, var(--pos) 55%, var(--surface))"),
    ("Neutral", "var(--warn)"),
    ("Sell", "color-mix(in srgb, var(--neg) 55%, var(--surface))"),
    ("Strong sell", "var(--neg)"),
]


def gauge(mark: float | None, counts: list[int] | None = None) -> str:
    """Semicircle consensus gauge with one arc per rating, strong buy on the left, strong sell on the right.

    ``mark`` is TradingView's 1-5 score; each rating owns one fifth of the arc (same cut-offs as ``rating_label``).
    ``counts`` (analysts per rating, same order) are printed just outside their arc.
    """
    import math

    if mark is None:
        return '<p class="muted">No analyst ratings.</p>'
    cx, cy, r = 110, 104, 82
    pos = (min(5.5, max(0.5, mark)) - 0.5) / 5  # 0..1 along the arc; zone i covers [i/5, (i+1)/5)
    theta = math.pi * (1 - pos)
    x, y = cx + r * math.cos(theta), cy - r * math.sin(theta)

    def point(frac: float, radius: float) -> tuple[float, float]:
        t = math.pi * (1 - frac)
        return cx + radius * math.cos(t), cy - radius * math.sin(t)

    gap = 0.008
    arcs, nums = [], []
    for i, (_, color) in enumerate(GAUGE_ZONES):
        x0, y0 = point(i / 5 + gap, r)
        x1, y1 = point((i + 1) / 5 - gap, r)
        arcs.append(
            f'<path d="M{x0:.1f} {y0:.1f} A{r} {r} 0 0 1 {x1:.1f} {y1:.1f}" stroke="{color}" stroke-width="12" fill="none"/>'
        )
        if counts is not None:
            tx, ty = point((i + 0.5) / 5, r + 17)
            n = counts[i]
            nums.append(
                f'<text x="{tx:.1f}" y="{ty + 3.5:.1f}" text-anchor="middle" font-family="var(--mono)" font-size="11" '
                f'fill="{"var(--fg)" if n else "var(--faint)"}" font-weight="{600 if n else 400}">{n}</text>'
            )

    label, _ = rating_label(mark)
    return (
        f'<svg viewBox="0 0 220 138" width="100%" style="max-width:280px" role="img" '
        f'aria-label="Consensus {label}, score {mark:.2f} of 5">{"".join(arcs)}{"".join(nums)}'
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="var(--fg)" stroke="var(--surface)" stroke-width="3"/>'
        f'<text x="110" y="92" text-anchor="middle" font-family="var(--mono)" font-size="18" fill="var(--fg)">{label}</text>'
        f'<text x="110" y="116" text-anchor="middle" font-size="11" fill="var(--muted)">score {mark:.2f} of 5</text>'
        '<text x="28" y="132" text-anchor="middle" font-size="10" fill="var(--muted)">Strong buy</text>'
        '<text x="192" y="132" text-anchor="middle" font-size="10" fill="var(--muted)">Strong sell</text></svg>'
    )


def facts(r: TrackedTicker) -> str:
    """Return the details card rows: earnings date, all-time high, score and refresh times.
    Next refresh counts down to this ticker's own next fetch.
    Missing values render as dashes.
    """
    f = r.forecast
    secs = None if r.dead else max(0, r.next_fetch - int(time.time()))
    rows = [
        ("Next earnings", date_short(f.next_earnings) if f else "—"),
        ("All-time high", price_fmt(f.ath) if f else "—"),
        ("Rating score", f"{f.rating_mark:.2f} / 5" if f and f.rating_mark is not None else "—"),
        ("Last fetched", ago(r.fetched_at)),
        (
            "Next refresh",
            "—" if secs is None else "due now" if secs == 0 else f"in {duration(secs)}",
        ),
    ]
    return (
        '<dl class="facts" style="margin:0">'
        + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows)
        + "</dl>"
    )
