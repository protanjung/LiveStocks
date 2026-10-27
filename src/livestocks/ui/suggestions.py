"""Pure HTML builders for the daily stock suggestions shown on the dashboard and /suggestions.
They read the validated idx-suggestions/v1 JSON as plain dictionaries and escape every string.
No function in this module performs I/O or touches NiceGUI.
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from html import escape
from typing import Any, TypeGuard

from livestocks.domain import SuggestionReport
from livestocks.ui.components import CURRENCY, ago, price_fmt

ORDER = {"BUY": 0, "SELL": 1, "HOLD": 2}
TONES = {"BUY": "buy", "SELL": "sell", "HOLD": "hold"}
CHIP_TONES = {"BUY": "pos", "SELL": "neg", "HOLD": "warn"}


def parse_report(report: SuggestionReport) -> dict[str, Any]:
    """Parse a stored report's payload text into a dictionary.
    Returns an empty dictionary when the text is not a JSON object.
    The payload was validated on delivery, so this is only a safety net.
    """
    try:
        data = json.loads(report.payload)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def items_of(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the stock rows of a parsed report, BUY first, then SELL, then HOLD.
    Rows keep their delivered order within each action.
    A missing or malformed list gives no rows.
    """
    rows = data.get("suggestions")
    if not isinstance(rows, list):
        return []
    valid = [r for r in rows if isinstance(r, dict)]
    return sorted(valid, key=lambda r: ORDER.get(str(r.get("action")), 3))


def action_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    """Count stock rows by action, always with BUY, SELL and HOLD keys.
    Rows with another action are not counted.
    Used for the chips in the summary and the dashboard card.
    """
    counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
    for row in items:
        action = str(row.get("action"))
        if action in counts:
            counts[action] += 1
    return counts


def when(iso: str | None) -> str:
    """Format an ISO 8601 timestamp in the server's local time, such as '12 Oct 2026, 15:55'.
    Aware timestamps are converted to local time first; naive ones are taken to be local already.
    Text that does not parse is returned escaped, and None gives a dash.
    """
    if not iso:
        return "—"
    try:
        moment = datetime.fromisoformat(iso)
    except ValueError:
        return escape(iso)
    local = moment.astimezone() if moment.tzinfo else moment
    return f"{local.day} {local:%b %Y}, {local:%H:%M}"


def day_label(date: str) -> str:
    """Format a YYYY-MM-DD trading date as 'Mon 12 Oct'.
    Text that is not a date is returned unchanged, as plain text rather than HTML.
    Callers escape the result when they put it in markup, so the labels never double-escape.
    """
    try:
        d = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return date
    return f"{d:%a} {d.day} {d:%b}"


def action_pill(action: str) -> str:
    """Return the coloured pill for BUY, SELL or HOLD.
    It reuses the rating pill styles: green, red and amber, each with a dot.
    Any other text renders as a neutral escaped label.
    """
    tone = TONES.get(action)
    if tone is None:
        return f'<span class="muted">{escape(action)}</span>'
    return f'<span class="rate {tone}"><i></i>{action}</span>'


def count_chips(counts: dict[str, int]) -> str:
    """Return the BUY, SELL and HOLD count chips, leaving out zero counts.
    Chips use the green, red and amber chip styles.
    Returns an empty string when every count is zero.
    """
    return "".join(
        f'<span class="chip {CHIP_TONES[a]}">{n} {a}</span>' for a, n in counts.items() if n
    )


def _price(v: Any) -> str:
    return price_fmt(float(v)) if isinstance(v, int | float) and not isinstance(v, bool) else "—"


def report_head(data: dict[str, Any], received_at: int, now: int | None = None) -> str:
    """Return the summary of one report: date, IHSG, market line and action counts.
    Also says when the brief was generated and how long ago the app stored it.
    now overrides the clock for tests.
    """
    market: dict[str, Any] = data.get("market") or {}
    if not isinstance(market, dict):
        market = {}
    ihsg = market.get("ihsg_last")
    ihsg_html = (
        f'<span class="chip">IHSG {ihsg:,.2f}</span>'
        if isinstance(ihsg, int | float) and not isinstance(ihsg, bool)
        else ""
    )
    chips = count_chips(action_counts(items_of(data)))
    summary = escape(str(market.get("summary", "")))
    return (
        '<div class="card-body sug-head">'
        f'<div class="sug-chips">{ihsg_html}{chips}</div>'
        f'<p class="sug-summary">{summary}</p>'
        f'<div class="muted fine">Generated {when(data.get("generated_at"))} · stored {ago(received_at, now)}</div>'
        "</div>"
    )


def disclaimer(data: dict[str, Any]) -> str:
    """Return the report's own disclaimer line as a small muted paragraph.
    A fallback text is used when the report has none.
    The text is escaped.
    """
    text = str(data.get("disclaimer") or "Informational only, not financial advice.")
    return f'<p class="muted fine" style="margin:0">{escape(text)}</p>'


def _num(v: Any) -> TypeGuard[int | float]:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _metric(label: str, value: str, note: str = "", tone: str = "") -> str:
    cls = f"sug-m {tone}".strip()
    note_html = f"<small>{note}</small>" if note else ""
    return f'<div class="{cls}"><span>{label}</span><b class="num">{value}</b>{note_html}</div>'


def _entry_of(row: dict[str, Any]) -> dict[str, Any]:
    entry = row.get("entry")
    return entry if isinstance(entry, dict) else {}


def _lots_of(row: dict[str, Any]) -> int | None:
    """Return the lot count when it is a positive whole number, otherwise None.
    Booleans are rejected because bool is a subclass of int, so True would read as one lot.
    """
    lots = row.get("lots")
    if isinstance(lots, bool) or not isinstance(lots, int) or lots <= 0:
        return None
    return lots


def _cost(row: dict[str, Any]) -> str:
    """Estimated order value in the display currency: lots x 100 shares x entry price. Empty when unknown."""
    entry, lots = _entry_of(row), _lots_of(row)
    price = entry.get("price")
    if not (_num(price) and lots):
        return ""
    return f"≈ {CURRENCY} {price * lots * 100:,.0f}"


SPARK_W, SPARK_H, SPARK_PAD = 240, 64, 4
LEVEL_NAMES = {"entry": "Entry", "stop": "Stop", "tp1": "TP1"}


def sparkline(closes: Sequence[float], levels: dict[str, Any]) -> str:
    """Return a small inline SVG of closing prices with dashed entry, stop and TP1 lines.
    A level is drawn only when it lies within one price range of the closes, so a far-off level
    does not flatten the line. Fewer than two closes give a short notice instead.
    """
    if len(closes) < 2:
        return '<div class="sug-spark none muted fine">No price history yet</div>'
    lo, hi = min(closes), max(closes)
    span = (hi - lo) or 1.0
    shown = {k: float(v) for k, v in levels.items() if _num(v) and lo - span <= v <= hi + span}
    lo, hi = min([lo, *shown.values()]), max([hi, *shown.values()])
    span = (hi - lo) or 1.0

    def y(v: float) -> float:
        return SPARK_PAD + (hi - v) / span * (SPARK_H - 2 * SPARK_PAD)

    step = SPARK_W / (len(closes) - 1)
    points = " ".join(f"{i * step:.1f},{y(c):.1f}" for i, c in enumerate(closes))
    lines = "".join(
        f'<line class="lv {k}" x1="0" x2="{SPARK_W}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
        for k, v in shown.items()
    )
    change = closes[-1] / closes[0] - 1 if closes[0] else 0.0
    tone = "pos" if change >= 0 else "neg"
    legend = "".join(f'<span class="lvl {k}">{LEVEL_NAMES[k]}</span>' for k in shown)
    return (
        f'<div class="sug-spark {tone}">'
        f'<svg viewBox="0 0 {SPARK_W} {SPARK_H}" role="img" '
        f'aria-label="Price over the last {len(closes)} sessions, {change * 100:+.2f}%">'
        f'<polygon class="area" points="0,{SPARK_H} {points} {SPARK_W},{SPARK_H}"/>'
        f"{lines}"
        f'<polyline class="ln" points="{points}"/>'
        f'<circle class="end" cx="{SPARK_W}" cy="{y(closes[-1]):.1f}" r="3"/></svg>'
        f'<div class="cap muted fine"><span>{len(closes)} sessions</span>{legend}'
        f'<span class="chg {tone}">{"−" if change < 0 else "+"}{abs(change) * 100:.2f}%</span></div>'
        "</div>"
    )


def stock_card(row: dict[str, Any], closes: Sequence[float] | None = None) -> str:
    """Return the card of one stock row: action, levels, risk to reward and the reason.
    closes adds a price sparkline marked with the entry, stop and TP1 levels.
    None leaves the chart out; an empty list shows that there is no history yet.
    """
    action = str(row.get("action", ""))
    tone = TONES.get(action, "")
    ticker = escape(str(row.get("ticker", "?")))
    name = escape(str(row.get("name", "")))
    lots = _lots_of(row)
    entry = _entry_of(row)
    zone = (
        f"{_price(entry.get('low'))} – {_price(entry.get('high'))}"
        if entry.get("low") or entry.get("high")
        else ""
    )
    stop_pct = row.get("stop_pct")
    stop_note = f"{'−' if stop_pct <= 0 else '+'}{abs(stop_pct):.2f}%" if _num(stop_pct) else ""
    rr = row.get("rr")
    weight = row.get("post_trade_weight_pct")
    badges = (
        f'<span class="chip">{"held" if row.get("held") else "new idea"}</span>'
        + ("" if row.get("verified") else '<span class="chip warn">unverified</span>')
        + (f'<span class="chip">weight after {weight:.2f}%</span>' if _num(weight) else "")
    )
    has_levels = any(_num(v) for v in (entry.get("price"), row.get("stop"), row.get("tp1")))
    show_lots = action != "HOLD" and lots is not None
    metrics = (
        '<div class="sug-metrics">'
        + "".join(
            (
                _metric("Lots", str(lots) if show_lots else "—", _cost(row)),
                _metric("Entry", _price(entry.get("price")), zone),
                _metric("Stop", _price(row.get("stop")), stop_note, "neg"),
                _metric("TP1", _price(row.get("tp1")), "", "pos"),
                _metric("TP2", _price(row.get("tp2")), "", "pos"),
                _metric("R : R", f"1 : {rr:.1f}" if _num(rr) else "—"),
            )
        )
        + "</div>"
        if has_levels
        else ""
    )
    chart = (
        ""
        if closes is None
        else sparkline(
            closes, {"entry": entry.get("price"), "stop": row.get("stop"), "tp1": row.get("tp1")}
        )
    )
    return (
        f'<article class="sug-card {tone}">'
        f'<header><div class="tk"><div><b>{ticker}</b><span class="nm">{name}</span></div></div>'
        f"{action_pill(action)}</header>"
        f'<div class="sug-badges">{badges}</div>'
        f"{chart}{metrics}"
        f'<p class="sug-why">{escape(str(row.get("reason", "")))}</p>'
        "</article>"
    )


def suggestion_cards(items: list[dict[str, Any]], history: dict[str, list[float]]) -> str:
    """Return the grid of stock cards, each with the price sparkline from history.
    history maps a ticker to its closing prices, oldest first; a missing ticker has no history yet.
    An empty list gives a short notice instead of a grid.
    """
    if not items:
        return '<div class="card-body muted">This report has no stock rows.</div>'
    cards = "".join(stock_card(r, history.get(str(r.get("ticker")), [])) for r in items)
    return f'<div class="card-body"><div class="sug-grid">{cards}</div></div>'


def _hold_list(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    lines = "".join(
        f"<li><b>{escape(str(r.get('ticker', '?')))}</b>"
        f'<span class="muted">{escape(str(r.get("reason", "")))}</span></li>'
        for r in rows
    )
    plural = "" if len(rows) == 1 else "s"
    return (
        f'<details class="sug-hold"><summary>{action_pill("HOLD")}'
        f'<span class="muted">{len(rows)} stock{plural} to keep as is</span>'
        f"</summary><ul>{lines}</ul></details>"
    )


def dashboard_card(
    data: dict[str, Any], date: str, received_at: int, now: int | None = None
) -> str:
    """Return the detailed card shown on the dashboard for the newest report.
    It has the market summary, counts, a card per BUY and SELL row, a HOLD list and the disclaimer.
    now overrides the clock for tests.
    """
    items = items_of(data)
    moves = [r for r in items if r.get("action") in ("BUY", "SELL")]
    holds = [r for r in items if r.get("action") == "HOLD"]
    cards = "".join(stock_card(r) for r in moves)
    if not cards:
        cards = '<div class="muted">Nothing to buy or sell. Hold everything.</div>'
    market = data.get("market")
    market = market if isinstance(market, dict) else {}
    ihsg = market.get("ihsg_last")
    ihsg_html = f'<span class="chip">IHSG {ihsg:,.2f}</span>' if _num(ihsg) else ""
    summary = escape(str(market.get("summary", "")))
    summary_html = f'<p class="sug-summary">{summary}</p>' if summary else ""
    return (
        '<section class="card sug-dash" aria-label="Daily suggestions">'
        '<div class="card-head"><h2>Daily suggestions</h2>'
        f'<span class="sub">{escape(day_label(date))} · stored {ago(received_at, now)}</span>'
        '<a class="btn ghost fine" style="text-decoration:none" href="/suggestions">All suggestions →</a></div>'
        '<div class="card-body sug-head">'
        f'<div class="sug-chips">{ihsg_html}{count_chips(action_counts(items))}</div>'
        f"{summary_html}"
        f'<div class="muted fine">Generated {when(data.get("generated_at"))}</div>'
        f'<div class="sug-grid">{cards}</div>'
        f"{_hold_list(holds)}"
        f"{disclaimer(data)}"
        "</div></section>"
    )
