"""Dividend views: the per-ticker dividend card and the market dividend calendar.
Pure HTML builders with escaped text. The four dates are Cum Date, Ex Date, Recording Date and Payment Date.
Dates are shown in the server's local time, the same as the earnings date.
"""

import calendar
from datetime import date, datetime
from html import escape

from livestocks.domain import CalendarEntry, CalendarKind, Dividend, shift_trading_days
from livestocks.ui.components import date_short, fmt
from livestocks.ui.primitives import card, th

HISTORY_ROWS = 8
MAX_CHIPS = 3  # calendar chips shown per day before the rest collapse into a count
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")  # the grid shows trading days only
SECTIONS = (
    (CalendarKind.UPCOMING, "Upcoming Ex Dates", "announced, the price adjusts on the Ex Date"),
    (CalendarKind.PAYING, "Awaiting Payment Date", "past the Ex Date, payment still ahead"),
    (CalendarKind.RECENT, "Recent Ex Dates", "Ex Date within the last month"),
)
# Column widths shared by every calendar table so the three cards line up.
TABLE_COLUMNS = ("28%", "12%", "12%", "16%", "14%", "9%", "9%")
# Chip labels, the full term each one stands for, and the chip colour class.
CHIP_LABEL = {"CUM": "CUM", "EX": "EX", "REC": "REC", "PAY": "PAY"}
TERM = {
    "CUM": "Cum Date",
    "EX": "Ex Date",
    "REC": "Recording Date",
    "PAY": "Payment Date",
}
CHIP_CLASS = {"CUM": "cum", "EX": "pos", "REC": "rec", "PAY": "warn"}


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


def _cum(ex: int | None) -> int | None:
    """Return the Cum Date derived from an Ex Date: the trading day before it, or None without one."""
    return None if ex is None else shift_trading_days(ex, -1)


def _record(ex: int | None, record: int | None) -> int | None:
    """Return the stored Recording Date, or the one derived from the Ex Date when none was stored."""
    if record is not None:
        return record
    return None if ex is None else shift_trading_days(ex, 1)


def dividend_card(d: Dividend, now: int) -> str:
    """Return the body of the detail page dividend card: the four dates, amount and history.
    An announced dividend is shown as such; otherwise the card says none is announced yet.
    The history lists recent payments newest first, with dashes for missing dates.
    """
    rows = [
        ("Cum Date", date_short(_cum(d.next_ex)) if d.next_ex else "none announced"),
        ("Ex Date", date_short(d.next_ex)),
        ("Recording Date", date_short(_record(d.next_ex, d.next_record))),
        ("Payment Date", date_short(d.next_pay)),
        ("Amount (IDR)", _amount(d.next_amount)),
        ("Last paid", f"{date_short(d.last_pay)} · {_amount(d.last_amount)}"),
        ("Yield", _pct(d.yield_pct)),
    ]
    facts = (
        '<dl class="facts facts-flush">'
        + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows)
        + "</dl>"
    )
    history = "".join(
        f"<tr><td>{date_short(_cum(p.ex_date))}</td><td>{date_short(p.ex_date)}</td>"
        f"<td>{date_short(_record(p.ex_date, p.record_date))}</td>"
        f"<td class='r'>{date_short(p.pay_date)}</td>"
        f"<td class='r num'>{_amount(p.amount)}</td><td class='r'>{escape(p.kind or '—')}</td></tr>"
        for p in d.history[:HISTORY_ROWS]
    )
    table = (
        '<div class="tablewrap fin mt-12"><table class="fintable"><thead><tr>'
        f"{th('Cum Date')}{th('Ex Date')}{th('Recording Date')}"
        f"{th('Payment Date', classes='r')}{th('Amount (IDR)', classes='r')}{th('Type', classes='r')}"
        f"</tr></thead><tbody>{history}</tbody></table></div>"
        if history
        else ""
    )
    return facts + table


def _row(e: CalendarEntry) -> str:
    """Return one calendar table row linking to the ticker's detail page.
    The symbol links, and the company name follows it in muted text that is cut short when long.
    The four dates are shown in order, then the amount and yield.
    """
    href = escape(f"/t/{e.exchange}/{e.symbol}", quote=True)
    name = escape(e.name or e.symbol)
    cum = e.cum_date if e.cum_date is not None else _cum(e.ex_date)
    record = _record(e.ex_date, e.record_date)
    return (
        f'<tr><th><a class="cal-link" href="{href}">{escape(e.symbol)}</a>'
        f'<span class="muted cal-name">{name}</span></th>'
        f"<td>{date_short(cum)}</td><td>{date_short(e.ex_date)}</td>"
        f"<td>{date_short(record)}</td><td class='r'>{date_short(e.pay_date)}</td>"
        f"<td class='r num'>{_amount(e.amount)}</td><td class='r num'>{_pct(e.yield_pct)}</td></tr>"
    )


def calendar_sections(entries: list[CalendarEntry]) -> str:
    """Return one card per dividend stage that has rows, in the order the cycle runs.
    Each card lists its rows by Ex Date with the Cum, Recording and Payment Dates, amount and yield.
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
            f"{th('Ticker')}{th('Cum Date')}{th('Ex Date')}{th('Recording Date')}"
            f"{th('Payment Date', classes='r')}{th('Amount (IDR)', classes='r')}"
            f"{th('Yield', classes='r')}"
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


Mark = tuple[str, CalendarEntry]


def _marks(entries: list[CalendarEntry], year: int, month: int) -> dict[date, list[Mark]]:
    """Return every Cum, Ex, Recording and Payment date that falls in one month, grouped by local day.
    Each mark is (code, entry) with code one of CUM, EX, REC and PAY.
    Dates are converted to the server's local day, the same day the table shows.
    """
    marks: dict[date, list[Mark]] = {}
    for e in entries:
        dated = (
            ("CUM", e.cum_date if e.cum_date is not None else _cum(e.ex_date)),
            ("EX", e.ex_date),
            ("REC", _record(e.ex_date, e.record_date)),
            ("PAY", e.pay_date),
        )
        for code, ts in dated:
            if ts is None:
                continue
            day = datetime.fromtimestamp(ts).date()
            if day.year == year and day.month == month:
                marks.setdefault(day, []).append((code, e))
    return marks


def _chip(code: str, e: CalendarEntry) -> str:
    """Return one chip for a date: its short code, the symbol, and the full term with the name in the tooltip."""
    title = escape(f"{TERM[code]} · {e.name or e.symbol}", quote=True)
    return (
        f'<span class="chip {CHIP_CLASS[code]} cal-chip" title="{title}">'
        f"{CHIP_LABEL[code]} {escape(e.symbol)}</span>"
    )


def _legend() -> str:
    """Return the key that explains the four chips above the grid and agenda."""
    return (
        '<div class="legend cal-legend">'
        '<span><span class="chip cum">CUM</span>Cum Date, last day to buy</span>'
        '<span><span class="chip pos">EX</span>Ex Date, the price adjusts</span>'
        '<span><span class="chip rec">REC</span>Recording Date</span>'
        '<span><span class="chip warn">PAY</span>Payment Date</span>'
        "</div>"
    )


def _grid(marks: dict[date, list[Mark]], year: int, month: int, today: date) -> str:
    """Return the wide-screen month grid: trading days only, Monday first, blanks outside the month.
    Today is outlined, and each day is labelled for assistive technology with its date and event count.
    """
    head = "".join(f'<div class="cal-head" aria-hidden="true">{d}</div>' for d in WEEKDAYS)
    cells: list[str] = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        for day in week:
            if day.weekday() >= 5:
                continue
            if day.month != month:
                cells.append('<div class="cal-cell blank" aria-hidden="true"></div>')
                continue
            events = marks.get(day, [])
            chips = [_chip(code, e) for code, e in events[:MAX_CHIPS]]
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


def _weekend_note(marks: dict[date, list[Mark]]) -> str:
    """Return a line naming the dates that fall on a Saturday or Sunday, which the grid leaves out.
    Empty when no date of the month is on a weekend, so the note appears only when it is needed.
    """
    weekend = [d for d in sorted(marks) if d.weekday() >= 5]
    if not weekend:
        return ""
    parts = [
        f"{d:%a %d %b}: " + ", ".join(f"{CHIP_LABEL[code]} {e.symbol}" for code, e in marks[d])
        for d in weekend
    ]
    return f'<p class="muted cal-weekend">Also on a weekend, shown in the list below: {escape("; ".join(parts))}</p>'


def _agenda(marks: dict[date, list[Mark]]) -> str:
    """Return the narrow-screen agenda: one entry per day that has events, oldest first.
    Weekend dates appear here too, since the agenda lists the days that have events rather than a grid.
    """
    items: list[str] = []
    for day in sorted(marks):
        chips = "".join(_chip(code, e) for code, e in marks[day])
        items.append(
            f'<li class="cal-day-row"><time datetime="{day.isoformat()}">{day:%a %d %b}</time>'
            f'<div class="cal-day-chips">{chips}</div></li>'
        )
    return f'<ol class="cal-agenda">{"".join(items)}</ol>'


def month_grid(entries: list[CalendarEntry], year: int, month: int, today: date) -> str:
    """Return one month of the calendar: a trading-day grid on wide screens, an agenda on phones, and a legend.
    Each date is a chip for Cum, Ex, Recording or Payment. A day shows up to MAX_CHIPS chips, then a count.
    A month with no dates says so in words, so an empty grid is never mistaken for a loading one.
    """
    marks = _marks(entries, year, month)
    label = month_label(year, month)
    if not marks:
        body = f'<p class="muted cal-empty">No dividend dates in {calendar.month_name[month]}.</p>'
    else:
        body = _grid(marks, year, month, today) + _weekend_note(marks) + _agenda(marks)
    return (
        f'<div class="cal-month" role="region" aria-label="{escape(label, quote=True)}">'
        f"{_legend()}{body}</div>"
    )
