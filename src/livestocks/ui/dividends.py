"""Dividend views: the per-ticker dividend card and the market dividend calendar.
Pure HTML builders with escaped text, in the same style as the other ui modules.
Dates are shown in the server's local time, the same as the earnings date.
"""

import calendar
from datetime import date, datetime
from html import escape

from livestocks.domain import CalendarEntry, CalendarKind, Dividend
from livestocks.ui.components import date_short, fmt
from livestocks.ui.primitives import card, th

HISTORY_ROWS = 8
MAX_CHIPS = 3  # calendar chips shown per day before the rest collapse into a count
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
SECTIONS = (
    (CalendarKind.UPCOMING, "Upcoming ex-dates", "announced, price adjusts on the ex-date"),
    (CalendarKind.PAYING, "Paying soon", "went ex-dividend, payout still ahead"),
    (CalendarKind.RECENT, "Recently went ex-dividend", "ex-date in the last month"),
)
# Column widths shared by every calendar table so the three cards line up.
TABLE_COLUMNS = ("44%", "14%", "14%", "14%", "14%")


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
        ("Next amount (IDR)", _amount(d.next_amount)),
        ("Last paid", f"{date_short(d.last_pay)} · {_amount(d.last_amount)}"),
        ("Yield", _pct(d.yield_pct)),
    ]
    facts = (
        '<dl class="facts facts-flush">'
        + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows)
        + "</dl>"
    )
    history = "".join(
        f"<tr><td>{date_short(p.ex_date)}</td><td class='r'>{date_short(p.pay_date)}</td>"
        f"<td class='r num'>{_amount(p.amount)}</td><td class='r'>{escape(p.kind or '—')}</td></tr>"
        for p in d.history[:HISTORY_ROWS]
    )
    table = (
        '<div class="tablewrap fin mt-12"><table class="fintable"><thead><tr>'
        "<th>Ex-date</th><th class='r'>Paid</th><th class='r'>Amount (IDR)</th><th class='r'>Type</th>"
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
    href = escape(f"/t/{e.exchange}/{e.symbol}", quote=True)
    name = escape(e.name or e.symbol)
    return (
        f'<tr><th><a class="cal-link" href="{href}">{escape(e.symbol)}</a>'
        f'<span class="muted cal-name">{name}</span></th>'
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
        table = (
            f'<div class="tablewrap"><table class="fintable cal-table">'
            f"<colgroup>{cols}</colgroup><thead><tr>"
            f"{th('Ticker')}{th('Ex-date')}{th('Pay date', classes='r')}"
            f"{th('Amount (IDR)', classes='r')}{th('Yield', classes='r')}"
            f"</tr></thead><tbody>{body}</tbody></table></div>"
        )
        cards.append(card(title, table, sub=f"{len(rows)} · {note}", label=title, padded=False))
    if not cards:
        return ""
    return '<div class="cal-sections">' + "".join(cards) + "</div>"


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


def _marks(
    entries: list[CalendarEntry], year: int, month: int
) -> dict[date, list[tuple[str, CalendarEntry]]]:
    """Return the ex-dates (EX) and payouts (PAY) that fall in one month, grouped by local day.
    Dates are converted to the server's local day, the same day the table shows.
    """
    marks: dict[date, list[tuple[str, CalendarEntry]]] = {}
    for e in entries:
        for ts, prefix in ((e.ex_date, "EX"), (e.pay_date, "PAY")):
            if ts is None:
                continue
            day = datetime.fromtimestamp(ts).date()
            if day.year == year and day.month == month:
                marks.setdefault(day, []).append((prefix, e))
    return marks


def _chip(prefix: str, e: CalendarEntry) -> str:
    """Return one EX or PAY chip, with the company name in its tooltip."""
    kind = "pos" if prefix == "EX" else "warn"
    title = escape(f"{prefix} · {e.name or e.symbol}", quote=True)
    return f'<span class="chip {kind} cal-chip" title="{title}">{prefix} {escape(e.symbol)}</span>'


def _legend() -> str:
    """Return the key that explains the EX and PAY chips above the grid and agenda."""
    return (
        '<div class="legend cal-legend">'
        '<span><span class="chip pos">EX</span>ex-date, the price adjusts</span>'
        '<span><span class="chip warn">PAY</span>payout date</span></div>'
    )


def _grid(
    marks: dict[date, list[tuple[str, CalendarEntry]]], year: int, month: int, today: date
) -> str:
    """Return the wide-screen month grid: Monday first, blank days outside the month, today outlined.
    Each day is labelled for assistive technology with its date and how many events it has.
    """
    head = "".join(f'<div class="cal-head" aria-hidden="true">{d}</div>' for d in WEEKDAYS)
    cells: list[str] = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        for day in week:
            if day.month != month:
                cells.append('<div class="cal-cell blank" aria-hidden="true"></div>')
                continue
            events = marks.get(day, [])
            chips = [_chip(prefix, e) for prefix, e in events[:MAX_CHIPS]]
            if len(events) > MAX_CHIPS:
                chips.append(f'<span class="cal-more">+{len(events) - MAX_CHIPS} more</span>')
            label = f"{day.day} {calendar.month_name[month]}"
            if events:
                label += f", {len(events)} event{'s' if len(events) != 1 else ''}"
            current = ' aria-current="date"' if day == today else ""
            today_cls = " today" if day == today else ""
            cells.append(
                f'<div class="cal-cell{today_cls}" role="group" aria-label="{escape(label, quote=True)}"'
                f'{current}><span class="cal-day">{day.day}</span>{"".join(chips)}</div>'
            )
    return f'<div class="cal-scroll"><div class="cal-week">{head}{"".join(cells)}</div></div>'


def _agenda(marks: dict[date, list[tuple[str, CalendarEntry]]]) -> str:
    """Return the narrow-screen agenda: one entry per day that has events, oldest first.
    Shown instead of the grid on phones, where seven columns would not fit.
    """
    items: list[str] = []
    for day in sorted(marks):
        chips = "".join(_chip(prefix, e) for prefix, e in marks[day])
        items.append(
            f'<li class="cal-day-row"><time datetime="{day.isoformat()}">{day:%a %d %b}</time>'
            f'<div class="cal-day-chips">{chips}</div></li>'
        )
    return f'<ol class="cal-agenda">{"".join(items)}</ol>'


def month_grid(entries: list[CalendarEntry], year: int, month: int, today: date) -> str:
    """Return one month of the calendar: a grid on wide screens, an agenda on phones, and a legend.
    Ex-dates are marked EX and payouts PAY. A day shows up to MAX_CHIPS chips, then a count.
    A month with no dates says so in words, so an empty grid is never mistaken for a loading one.
    """
    marks = _marks(entries, year, month)
    label = month_label(year, month)
    if not marks:
        body = f'<p class="muted cal-empty">No dividend dates in {calendar.month_name[month]}.</p>'
    else:
        body = _grid(marks, year, month, today) + _agenda(marks)
    return f'<div class="cal-month" role="region" aria-label="{escape(label, quote=True)}">{_legend()}{body}</div>'
