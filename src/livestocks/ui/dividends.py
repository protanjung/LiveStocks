"""Dividend views: the per-ticker dividend card and the market dividend calendar.
Pure HTML builders with escaped text, in the same style as the other ui modules.
Dates are shown in the server's local time, the same as the earnings date.
"""

from html import escape

from livestocks.domain import CalendarEntry, CalendarKind, Dividend
from livestocks.ui.components import date_short, fmt

HISTORY_ROWS = 8
SECTIONS = (
    (CalendarKind.UPCOMING, "Upcoming ex-dates", "announced, price adjusts on the ex-date"),
    (CalendarKind.PAYING, "Paying soon", "went ex-dividend, payout still ahead"),
    (CalendarKind.RECENT, "Recently went ex-dividend", "ex-date in the last month"),
)


def _amount(v: float | None) -> str:
    """Format a per-share dividend with two decimals, or a dash when missing.
    Dividends are small enough that the decimals matter.
    """
    return fmt(v, 2)


def _pct(v: float | None) -> str:
    """Format a yield percentage with two decimals and a trailing percent sign.
    A missing yield renders a dash.
    """
    return "—" if v is None else f"{fmt(v, 2)}%"


def dividend_card(d: Dividend, now: int) -> str:
    """Return the body of the detail page dividend card: next dates, last payment and history.
    An announced dividend is shown as such; otherwise the card says none is announced yet.
    The history lists the most recent payments newest first, with dashes for missing dates; now is unix seconds.
    """
    upcoming = "none announced" if d.next_ex is None else date_short(d.next_ex)
    rows = [
        ("Next ex-date", upcoming),
        ("Next payment", date_short(d.next_pay)),
        ("Next amount", _amount(d.next_amount)),
        ("Last paid", f"{date_short(d.last_pay)} · {_amount(d.last_amount)}"),
        ("Yield", _pct(d.yield_pct)),
    ]
    facts = (
        '<dl class="facts" style="margin:0">'
        + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows)
        + "</dl>"
    )
    history = "".join(
        f"<tr><td>{date_short(p.ex_date)}</td><td class='r'>{date_short(p.pay_date)}</td>"
        f"<td class='r num'>{_amount(p.amount)}</td><td class='r'>{escape(p.kind or '—')}</td></tr>"
        for p in d.history[:HISTORY_ROWS]
    )
    table = (
        '<div class="tablewrap fin" style="margin-top:12px"><table class="fintable"><thead><tr>'
        "<th>Ex-date</th><th class='r'>Paid</th><th class='r'>Amount</th><th class='r'>Type</th>"
        f"</tr></thead><tbody>{history}</tbody></table></div>"
        if history
        else ""
    )
    return facts + table


def _row(e: CalendarEntry) -> str:
    """Return one calendar table row linking to the ticker's detail page.
    The symbol links, and the company name sits beside it in muted text.
    Dates and numbers follow the same formats as the detail card.
    """
    href = escape(f"/t/{e.exchange}/{e.symbol}")
    name = escape(e.name or e.symbol)
    return (
        f'<tr><th><a href="{href}" style="color:var(--accent)">{escape(e.symbol)}</a>'
        f'<span class="muted" style="margin-left:8px">{name}</span></th>'
        f"<td>{date_short(e.ex_date)}</td><td class='r'>{date_short(e.pay_date)}</td>"
        f"<td class='r num'>{_amount(e.amount)}</td><td class='r num'>{_pct(e.yield_pct)}</td></tr>"
    )


def calendar_sections(entries: list[CalendarEntry]) -> str:
    """Return one card per dividend stage that has rows, in the order the cycle runs.
    Each card lists its rows by ex-date with the payout date, amount and yield.
    Stages with no rows are left out, so an empty list returns an empty string.
    """
    cards: list[str] = []
    for kind, title, note in SECTIONS:
        rows = sorted((e for e in entries if e.kind is kind), key=lambda e: e.ex_date or 0)
        if not rows:
            continue
        body = "".join(_row(e) for e in rows)
        cards.append(
            '<section class="card">'
            f'<div class="card-head"><h2>{title}</h2><span class="sub">{len(rows)} · {note}</span></div>'
            '<div class="tablewrap"><table class="fintable"><thead><tr>'
            "<th>Ticker</th><th>Ex-date</th><th class='r'>Pay date</th>"
            "<th class='r'>Amount</th><th class='r'>Yield</th>"
            f"</tr></thead><tbody>{body}</tbody></table></div></section>"
        )
    if not cards:
        return ""
    return '<div style="display:grid;gap:20px">' + "".join(cards) + "</div>"
