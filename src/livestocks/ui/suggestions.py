"""Pure HTML builders for the daily stock suggestions shown on the dashboard and /suggestions.
They read the validated idx-suggestions/v1 JSON as plain dictionaries and escape every string.
No function in this module performs I/O or touches NiceGUI.
"""

import json
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any, TypeGuard

from livestocks.domain import SuggestionReport
from livestocks.ui.components import ago, price_fmt

ORDER = {"BUY": 0, "SELL": 1, "HOLD": 2}
TONES = {"BUY": "buy", "SELL": "sell", "HOLD": "hold"}
CHIP_TONES = {"BUY": "pos", "SELL": "neg", "HOLD": "warn"}
WIB = timedelta(hours=7)


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
    """Format an ISO 8601 timestamp as '12 Oct 2026, 08:55 WIB'.
    Offsets other than +07:00 are shown as UTC+hh:mm; text that does not parse is returned as is.
    None gives a dash.
    """
    if not iso:
        return "—"
    try:
        moment = datetime.fromisoformat(iso)
    except ValueError:
        return escape(iso)
    offset = moment.utcoffset()
    if offset is None:
        zone = ""
    elif offset == WIB:
        zone = " WIB"
    elif offset == timedelta(0):
        zone = " UTC"
    else:
        minutes = int(offset.total_seconds() // 60)
        sign = "+" if minutes >= 0 else "−"
        zone = f" UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"
    return f"{moment.day} {moment:%b %Y}, {moment:%H:%M}{zone}"


def day_label(date: str) -> str:
    """Format a YYYY-MM-DD trading date as 'Mon 12 Oct'.
    Text that is not a date is returned escaped and unchanged.
    Used on the date buttons of the suggestions page.
    """
    try:
        d = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return escape(date)
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


def _entry(entry: Any) -> str:
    if not isinstance(entry, dict):
        return '<span class="muted">—</span>'
    price, low, high = entry.get("price"), entry.get("low"), entry.get("high")
    if price is None and low is None and high is None:
        return '<span class="muted">—</span>'
    zone = f'<div class="muted fine">{_price(low)} – {_price(high)}</div>' if low or high else ""
    return f'<div class="num">{_price(price)}</div>{zone}'


def _stop(row: dict[str, Any]) -> str:
    stop, stop_pct = row.get("stop"), row.get("stop_pct")
    if stop is None:
        return '<span class="muted">—</span>'
    pct = (
        f'<div class="chg neg">{"−" if stop_pct <= 0 else "+"}{abs(stop_pct):.1f}%</div>'
        if isinstance(stop_pct, int | float)
        else ""
    )
    return f'<div class="num">{_price(stop)}</div>{pct}'


def _row(row: dict[str, Any]) -> str:
    action = str(row.get("action", ""))
    lots = row.get("lots")
    ticker = escape(str(row.get("ticker", "?")))
    name = escape(str(row.get("name", "")))
    held = "held" if row.get("held") else "new idea"
    flag = "" if row.get("verified") else '<span class="chip warn">unverified</span>'
    rr = row.get("rr")
    rr_html = f"1 : {rr:.1f}" if isinstance(rr, int | float) and not isinstance(rr, bool) else "—"
    weight = row.get("post_trade_weight_pct")
    weight_html = (
        f" · weight after {weight:.1f}%"
        if isinstance(weight, int | float) and not isinstance(weight, bool)
        else ""
    )
    why = escape(str(row.get("reason", "")))
    return (
        "<tr>"
        f'<td><div class="tk"><div><b>{ticker}</b><span class="nm">{name}</span></div></div></td>'
        f"<td>{action_pill(action)}</td>"
        f'<td class="r num">{lots if action != "HOLD" and isinstance(lots, int) else "—"}</td>'
        f'<td class="r">{_entry(row.get("entry"))}</td>'
        f'<td class="r num">{_price(row.get("tp1"))}<div class="muted fine">{_price(row.get("tp2"))}</div></td>'
        f'<td class="r">{_stop(row)}</td>'
        f'<td class="r num">{rr_html}</td>'
        "</tr>"
        f'<tr class="why"><td colspan="7"><span class="muted">{held}{weight_html}</span> {flag} {why}</td></tr>'
    )


def suggestion_table(items: list[dict[str, Any]]) -> str:
    """Return the table of stock rows: action, lots, entry, targets, stop and risk to reward.
    Each row is followed by a line with the reason and whether the levels are verified.
    An empty list gives a short notice instead of a table.
    """
    if not items:
        return '<div class="card-body muted">This report has no stock rows.</div>'
    head = (
        "<thead><tr><th>Ticker</th><th>Action</th>"
        '<th class="r">Lots</th><th class="r">Entry</th>'
        '<th class="r">TP1 / TP2</th><th class="r">Stop</th><th class="r">R:R</th></tr></thead>'
    )
    body = "".join(_row(r) for r in items)
    return (
        f'<div class="tablewrap"><table class="sugtable">{head}<tbody>{body}</tbody></table></div>'
    )


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


def _cost(row: dict[str, Any]) -> str:
    """Estimated order value in rupiah: lots x 100 shares x entry price. Empty when unknown."""
    entry, lots = _entry_of(row), row.get("lots")
    price = entry.get("price")
    if not (_num(price) and isinstance(lots, int) and lots > 0):
        return ""
    return f"≈ Rp {price * lots * 100:,.0f}"


def _move_card(row: dict[str, Any]) -> str:
    action = str(row.get("action", ""))
    tone = TONES.get(action, "")
    ticker = escape(str(row.get("ticker", "?")))
    name = escape(str(row.get("name", "")))
    lots = row.get("lots")
    entry = _entry_of(row)
    zone = (
        f"{_price(entry.get('low'))} – {_price(entry.get('high'))}"
        if entry.get("low") or entry.get("high")
        else ""
    )
    stop_pct = row.get("stop_pct")
    stop_note = f"{'−' if stop_pct <= 0 else '+'}{abs(stop_pct):.1f}%" if _num(stop_pct) else ""
    rr = row.get("rr")
    weight = row.get("post_trade_weight_pct")
    badges = (
        f'<span class="chip">{"held" if row.get("held") else "new idea"}</span>'
        + ("" if row.get("verified") else '<span class="chip warn">unverified</span>')
        + (f'<span class="chip">weight after {weight:.1f}%</span>' if _num(weight) else "")
    )
    metrics = "".join(
        (
            _metric("Lots", str(lots) if isinstance(lots, int) else "—", _cost(row)),
            _metric("Entry", _price(entry.get("price")), zone),
            _metric("Stop", _price(row.get("stop")), stop_note, "neg"),
            _metric("TP1", _price(row.get("tp1")), "", "pos"),
            _metric("TP2", _price(row.get("tp2")), "", "pos"),
            _metric("R : R", f"1 : {rr:.1f}" if _num(rr) else "—"),
        )
    )
    return (
        f'<article class="sug-card {tone}">'
        f'<header><div class="tk"><div><b>{ticker}</b><span class="nm">{name}</span></div></div>'
        f"{action_pill(action)}</header>"
        f'<div class="sug-badges">{badges}</div>'
        f'<div class="sug-metrics">{metrics}</div>'
        f'<p class="sug-why">{escape(str(row.get("reason", "")))}</p>'
        "</article>"
    )


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
    cards = "".join(_move_card(r) for r in moves)
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
        f'<span class="sub">{day_label(date)} · stored {ago(received_at, now)}</span>'
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
