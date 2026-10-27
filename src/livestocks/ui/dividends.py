"""Dividend views: the per-ticker dividend card and the market dividend calendar.
Pure HTML builders with escaped text, in the same style as the other ui modules.
Dates are shown in the server's local time, the same as the earnings date.
"""

import calendar
from datetime import date, datetime
from html import escape

from livestocks.domain import CalendarEntry, CalendarKind, Dividend
from livestocks.ui.components import date_short, fmt

HISTORY_ROWS = 8
MAX_CHIPS = 3  # calendar chips shown per day before the rest collapse into a count
SECTIONS = (
    (CalendarKind.UPCOMING, "Upcoming ex-dates", "announced, price adjusts on the ex-date"),
    (CalendarKind.PAYING, "Paying soon", "went ex-dividend, payout still ahead"),
    (CalendarKind.RECENT, "Recently went ex-dividend", "ex-date in the last month"),
)
# Column widths shared by every calendar table so the three cards line up.
TABLE_COLUMNS = ("44%", "14%", "14%", "14%", "14%")
_TABLE = "table-layout:fixed;width:100%;min-width:560px"
_NAME = "display:inline-block;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:bottom"
_WEEK = "display:grid;grid-template-columns:repeat(7,minmax(96px,1fr));gap:6px;min-width:700px"
_HEAD = (
    "font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;padding:0 4px"
)
_CELL = (
    "min-height:76px;border:1px solid var(--line);border-radius:8px;padding:4px;"
    "display:grid;align-content:start;gap:3px;min-width:0"
)
_TODAY = ";border-color:var(--accent)"
_DAY = "font-size:12px;color:var(--muted);font-family:var(--mono)"
_CHIP = "display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px"
_MORE = "font-size:11px;color:var(--muted)"


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
    The history lists recent payments newest first, with dashes for missing dates.
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
    The symbol links, and the company name follows it in muted text that is cut short when long.
    Dates and numbers follow the same formats as the detail card.
    """
    href = escape(f"/t/{e.exchange}/{e.symbol}")
    name = escape(e.name or e.symbol)
    return (
        f'<tr><th><a href="{href}" style="color:var(--accent)">{escape(e.symbol)}</a>'
        f'<span class="muted" style="margin-left:8px;{_NAME}">{name}</span></th>'
        f"<td>{date_short(e.ex_date)}</td><td class='r'>{date_short(e.pay_date)}</td>"
        f"<td class='r num'>{_amount(e.amount)}</td><td class='r num'>{_pct(e.yield_pct)}</td></tr>"
    )


def calendar_sections(entries: list[CalendarEntry]) -> str:
    """Return one card per dividend stage that has rows, in the order the cycle runs.
    Each card lists its rows by ex-date with the payout date, amount and yield.
    Stages with no rows are left out, so an empty list returns an empty string.
    """
    cols = "".join(f'<col style="width:{w}">' for w in TABLE_COLUMNS)
    cards: list[str] = []
    for kind, title, note in SECTIONS:
        rows = sorted((e for e in entries if e.kind is kind), key=lambda e: e.ex_date or 0)
        if not rows:
            continue
        body = "".join(_row(e) for e in rows)
        cards.append(
            '<section class="card">'
            f'<div class="card-head"><h2>{title}</h2><span class="sub">{len(rows)} · {note}</span></div>'
            '<div class="tablewrap"><table class="fintable" '
            f'style="{_TABLE}"><colgroup>{cols}</colgroup><thead><tr>'
            "<th>Ticker</th><th>Ex-date</th><th class='r'>Pay date</th>"
            "<th class='r'>Amount</th><th class='r'>Yield</th>"
            f"</tr></thead><tbody>{body}</tbody></table></div></section>"
        )
    if not cards:
        return ""
    return '<div style="display:grid;gap:20px">' + "".join(cards) + "</div>"


def month_of(today: date, offset: int) -> tuple[int, int]:
    """Return the (year, month) that is offset months from today's month.
    Negative offsets go back, and the arithmetic carries across year boundaries.
    Used by the calendar page's previous, next and today buttons.
    """
    index = today.month - 1 + offset
    return today.year + index // 12, index % 12 + 1


def month_label(year: int, month: int) -> str:
    """Return the month and year as 'May 2026', for the calendar heading.
    Month names are English, matching the rest of the interface.
    The year follows the month so the heading reads naturally.
    """
    return f"{calendar.month_name[month]} {year}"


def month_grid(entries: list[CalendarEntry], year: int, month: int, today: date) -> str:
    """Return a Monday-first month grid with each day's ex-dates and payouts as chips.
    Ex-dates are marked EX and payouts PAY; a day shows up to MAX_CHIPS chips, then a count.
    Days outside the month are left blank so every week keeps seven columns, and today is outlined.
    """
    marks: dict[date, list[str]] = {}
    for e in entries:
        for ts, prefix, cls in ((e.ex_date, "EX", "pos"), (e.pay_date, "PAY", "")):
            if ts is None:
                continue
            day = datetime.fromtimestamp(ts).date()
            if day.year == year and day.month == month:
                chip = (
                    f'<span class="chip {cls}" style="{_CHIP}">{prefix} {escape(e.symbol)}</span>'
                )
                marks.setdefault(day, []).append(chip)

    head = "".join(
        f'<div style="{_HEAD}">{name}</div>'
        for name in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    )
    cells: list[str] = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        for day in week:
            if day.month != month:
                cells.append("<div></div>")
                continue
            chips = marks.get(day, [])
            shown = chips[:MAX_CHIPS]
            if len(chips) > MAX_CHIPS:
                shown.append(f'<span style="{_MORE}">+{len(chips) - MAX_CHIPS} more</span>')
            style = _CELL + (_TODAY if day == today else "")
            cells.append(
                f'<div style="{style}"><span style="{_DAY}">{day.day}</span>{"".join(shown)}</div>'
            )
    return f'<div class="tablewrap"><div style="{_WEEK}">{head}{"".join(cells)}</div></div>'
