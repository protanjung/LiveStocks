"""Dividend-hunting views: the controls, the ranked table with timelines, the detail and the guide.
Pure HTML builders with escaped text. Rows are ranked by hunt score, and each row draws its four dates.
Clicks carry data-act and data-key attributes, which the calendar page handles in one place.
"""

from collections.abc import Iterable
from datetime import date, datetime, time
from html import escape

from livestocks.domain import (
    CalendarEntry,
    CalendarKind,
    Check,
    CheckStatus,
    HuntStyle,
    hunt_checks,
    hunt_score,
)
from livestocks.ui.components import date_short, fmt
from livestocks.ui.models import PageState
from livestocks.ui.primitives import th, trunc

WINDOW_DAYS = 42  # the timeline shows six weeks from today
FILTERS = (
    ("event", "Event yield ≥ 2%"),
    ("payout", "Payout ≤ 90%"),
    ("streak", "Streak ≥ 3 yrs"),
    ("trap", "Hide trap risk"),
    ("past", "Show past"),
)
MARKERS = (
    ("C", "cum", "Cum Date"),
    ("E", "ex", "Ex Date"),
    ("R", "rec", "Recording Date"),
    ("P", "pay", "Payment Date"),
)
STATUS_MARK = {
    CheckStatus.PASS: "✓ Pass",
    CheckStatus.WARN: "! Warn",
    CheckStatus.FAIL: "✕ Fail",
    CheckStatus.NA: "– n/a",
}
TRAP_LABEL = {"low": "Low", "med": "Medium", "high": "High"}
TRAP_CLASS = {"low": "pos", "med": "warn", "high": "neg"}


def key_of(entry: CalendarEntry) -> str:
    """Return the EXCHANGE:SYMBOL key that names a row in clicks and in the selection.
    The same key is used by the page state and by the data-key attribute of each row.
    It matches the key format used for tickers elsewhere in the app.
    """
    return f"{entry.exchange}:{entry.symbol}"


def apply_action(state: PageState, action: str, value: str) -> bool:
    """Apply one click from the controls or the table to the page state; True if anything changed.
    Actions are style, view, filter (toggle), select and help (toggle); unknown ones are ignored.
    Values are checked against the known choices, so a forged click cannot put the state out of range.
    """
    if action == "style" and value in (HuntStyle.SHORT, HuntStyle.LONG):
        state.style = value
    elif action == "view" and value in ("hunt", "month"):
        state.view = value
    elif action == "filter" and value in {key for key, _ in FILTERS}:
        state.filters = state.filters ^ {value}
    elif action == "select":
        state.selected = value
    elif action == "help":
        state.help = not state.help
    else:
        return False
    return True


def _passes(e: CalendarEntry, filters: frozenset[str]) -> bool:
    """Return True when an entry satisfies every active filter; a missing figure fails its filter."""
    if "past" not in filters and e.kind is CalendarKind.RECENT:
        return False
    if "event" in filters and (e.event_yield is None or e.event_yield < 2):
        return False
    if "payout" in filters and (e.payout is None or e.payout > 90):
        return False
    if "streak" in filters and (e.streak_years is None or e.streak_years < 3):
        return False
    return not ("trap" in filters and e.trap and e.trap.level in ("med", "high"))


def ranked(
    entries: Iterable[CalendarEntry], style: HuntStyle, filters: frozenset[str]
) -> list[tuple[CalendarEntry, int | None]]:
    """Return the entries that pass the filters, best hunt score first, unscored ones last.
    Ties are broken by the sooner Ex Date, then by symbol, so the order is stable between refreshes.
    Past dividends are left out unless the 'past' filter is on.
    """
    rows = [(e, hunt_score(e, style)) for e in entries if _passes(e, filters)]
    rows.sort(key=lambda r: (-(r[1] if r[1] is not None else -1), r[0].ex_date or 0, r[0].symbol))
    return rows


def _seg(label: str, act: str, options: tuple[tuple[str, str], ...], current: str) -> str:
    """Return a segmented control of buttons; the current option is pressed."""
    buttons = "".join(
        f'<button type="button" data-act="{act}" data-key="{key}" '
        f'aria-pressed="{str(key == current).lower()}">{escape(text)}</button>'
        for key, text in options
    )
    return f'<div class="seg" role="group" aria-label="{escape(label)}">{buttons}</div>'


def controls(style: HuntStyle, view: str, filters: frozenset[str], help_open: bool) -> str:
    """Return the control bar: style switch, view switch, help button and, in the hunt view, filters.
    Every control is a real button carrying data-act and data-key for the page's click handler.
    Pressed state is exposed with aria-pressed, so the current choice is not shown by colour alone.
    """
    style_seg = _seg(
        "Hunting style",
        "style",
        ((HuntStyle.SHORT, "Short-term hunter"), (HuntStyle.LONG, "Long-term income")),
        style,
    )
    view_seg = _seg("View", "view", (("hunt", "Hunt"), ("month", "Month")), view)
    chips = ""
    if view == "hunt":
        chips = (
            '<div class="hunt-filters" role="group" aria-label="Filters">'
            + "".join(
                f'<button type="button" class="fchip" data-act="filter" data-key="{key}" '
                f'aria-pressed="{str(key in filters).lower()}">{escape(text)}</button>'
                for key, text in FILTERS
            )
            + "</div>"
        )
    helper = (
        f'<button type="button" class="btn ghost fine" data-act="help" '
        f'aria-expanded="{str(help_open).lower()}">How to use</button>'
    )
    return f'<div class="hunt-controls">{style_seg}{view_seg}{helper}{chips}</div>'


def _marks(e: CalendarEntry) -> list[tuple[str, str, str, int, bool]]:
    """Return the dated markers of an entry as (letter, class, term, timestamp, estimated)."""
    dated = (
        ("C", "cum", "Cum Date", e.cum_date, True),
        ("E", "ex", "Ex Date", e.ex_date, False),
        ("R", "rec", "Recording Date", e.record_date, not e.record_real),
        ("P", "pay", "Payment Date", e.pay_date, False),
    )
    return [(a, b, c, ts, est) for a, b, c, ts, est in dated if ts is not None]


def _lane(e: CalendarEntry, start: float) -> str:
    """Return the timeline of one row: a bar over the holding window and a dot per upcoming date.
    Positions are days from today across the six-week window; dates past it sit at its edge.
    Dates already behind us are not drawn, only noted in words, and close dots are nudged apart.
    """
    span = WINDOW_DAYS * 86400
    marks = sorted((m for m in _marks(e) if m[3] >= start), key=lambda m: m[3])
    dots: list[str] = []
    previous, shift = -100.0, 0
    for letter, cls, term, ts, est in marks:
        pos = min(max((ts - start) / span * 100, 0.0), 98.0)
        shift = shift + 14 if pos - previous < 3.0 else 0
        previous = pos
        tip = f"{term}: {date_short(ts)}" + (" (est.)" if est else "")
        dots.append(
            f'<span class="hdot {cls}" style="left:{pos:.2f}%;margin-left:{shift}px" '
            f'title="{escape(tip, quote=True)}">{letter}</span>'
        )
    bar = ""
    if marks:
        first, last = marks[0][3], marks[-1][3]
        left = min(max((first - start) / span * 100, 0.0), 98.0)
        right = min(max((last - start) / span * 100, 0.0), 98.0)
        bar = f'<span class="hbar" style="left:{left:.2f}%;width:{max(right - left, 0.5):.2f}%"></span>'
    note = ""
    if e.ex_date is not None and e.ex_date < start:
        note = f'<span class="hnote">Ex passed {escape(date_short(e.ex_date, year=False))}</span>'
    return f'<div class="hlane">{bar}{note}{"".join(dots)}</div>'


def _tone(good: bool, bad: bool) -> str:
    """Return the colour class for a figure: pos when good, neg when bad, warn in between."""
    return "pos" if good else "neg" if bad else "warn"


def _row(e: CalendarEntry, score: int | None, selected: bool, start: float) -> str:
    """Return one table row: ticker, the guide's figures, the score and the timeline."""
    key = escape(key_of(e), quote=True)
    ey, p = e.event_yield, e.payout
    level = e.trap.level if e.trap else None
    hits = ""
    if e.trap and level:
        n = len(e.trap.events)
        hits = f"The drop beat the dividend in {round((e.trap.trap_rate or 0) * n)} of {n} Ex Dates"
    trap_cell = (
        f'<span class="{TRAP_CLASS[level]}" title="{escape(hits, quote=True)}">{TRAP_LABEL[level]}</span>'
        if level
        else '<span class="muted" title="Not enough Ex Date history yet">—</span>'
    )
    payout_cell = (
        "—" if p is None else f'<span class="{_tone(30 <= p <= 70, p > 90)}">{fmt(p, 0)}%</span>'
    )
    return (
        f'<tr class="hrow{" sel" if selected else ""}" data-act="select" data-key="{key}" '
        f'aria-selected="{str(selected).lower()}">'
        f'<th scope="row"><button type="button" class="linkish" data-act="select" data-key="{key}">'
        f"<b>{escape(e.symbol)}</b></button>{trunc(e.name or e.symbol)}</th>"
        f"<td class='r num pos'>{'—' if ey is None else fmt(ey, 2) + '%'}</td>"
        f"<td class='r num'>{'—' if e.yield_pct is None else fmt(e.yield_pct, 1) + '%'}</td>"
        f"<td class='r num'>{payout_cell}</td>"
        f"<td class='r num'>{'—' if e.streak_years is None else e.streak_years}</td>"
        f"<td>{trap_cell}</td>"
        f"<td class='r num'><b>{'—' if score is None else score}</b></td>"
        f'<td class="tl">{_lane(e, start)}</td></tr>'
    )


def hunt_table(
    rows: list[tuple[CalendarEntry, int | None]], selected: str | None, today: date
) -> str:
    """Return the ranked table: one row per dividend with its figures, score and six-week timeline.
    The row whose key equals selected is highlighted; an empty list gives a message instead.
    The header shows the week starting dates over the timeline column.
    """
    if not rows:
        return (
            '<p class="muted hunt-empty">No dividend matches these filters. '
            "Turn a filter off, or switch on Show past, to see more.</p>"
        )
    start = datetime.combine(today, time.min).timestamp()
    weeks = "".join(
        f"<span>{date_short(int(start) + 7 * i * 86400, year=False)}</span>"
        for i in range(WINDOW_DAYS // 7)
    )
    cols = "".join(
        f'<col style="width:{w}">'
        for w in ("160px", "74px", "64px", "70px", "66px", "76px", "58px", "auto")
    )
    head = (
        f"{th('Ticker')}{th('Event', classes='r')}{th('Yield', classes='r')}"
        f"{th('Payout', classes='r')}{th('Streak', classes='r')}{th('Trap')}"
        f"{th('Score', classes='r')}"
        f'<th scope="col" class="tl"><div class="hweeks">{weeks}</div></th>'
    )
    body = "".join(_row(e, s, key_of(e) == selected, start) for e, s in rows)
    return (
        '<div class="tablewrap"><table class="hunt-table">'
        f"<colgroup>{cols}</colgroup><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _check_item(c: Check) -> str:
    """Return one checklist line: the status word and mark, the label and the numbers behind it."""
    return (
        f'<li class="chk {c.status}"><span class="chk-mark">{STATUS_MARK[c.status]}</span>'
        f"<b>{escape(c.label)}</b> <span class='muted'>{escape(c.detail)}</span></li>"
    )


def hunt_detail(entry: CalendarEntry, style: HuntStyle) -> str:
    """Return the detail panel of one dividend: its four dates, the guide checklist and trap history.
    Cum Date and a derived Recording Date are marked est., since the feeds do not publish them.
    The trap table lists the last Ex Dates with the price drop against the dividend paid.
    """
    score = hunt_score(entry, style)
    rec_note = "" if entry.record_real else " <span class='muted'>(est.)</span>"
    href = escape(f"/t/{entry.exchange}/{entry.symbol}", quote=True)
    dates = (
        f"<dt>Cum Date</dt><dd>{date_short(entry.cum_date)} <span class='muted'>(est.)</span></dd>"
        f"<dt>Ex Date</dt><dd>{date_short(entry.ex_date)}</dd>"
        f"<dt>Recording Date</dt><dd>{date_short(entry.record_date)}{rec_note}</dd>"
        f"<dt>Payment Date</dt><dd>{date_short(entry.pay_date)}</dd>"
        f"<dt>Amount</dt><dd>IDR {fmt(entry.amount, 2)}"
        f"{'' if entry.event_yield is None else ' · ' + fmt(entry.event_yield, 2) + '%'}</dd>"
        f"<dt>Price</dt><dd>{'—' if entry.price is None else 'IDR ' + fmt(entry.price, 0)}</dd>"
    )
    head = (
        f'<div class="hd-head"><h2>{escape(entry.symbol)}</h2>'
        f'<span class="muted">{escape(entry.name or "")}'
        f"{' · ' + escape(entry.sector) if entry.sector else ''}</span>"
        f'<span class="hd-score">Score {"—" if score is None else score}</span></div>'
    )
    checks = "".join(_check_item(c) for c in hunt_checks(entry))
    trap = _trap_card(entry)
    return (
        '<div class="hunt-detail">'
        f'<section class="card hd-card" aria-label="Dates">{head}'
        f'<dl class="hd-dates">{dates}</dl>'
        f'<a class="cal-link" href="{href}">Open ticker page →</a></section>'
        f'<section class="card hd-card" aria-label="Checklist"><h2>Guide checklist</h2>'
        f'<ul class="hd-checks">{checks}</ul></section>'
        f'<section class="card hd-card" aria-label="Trap history"><h2>Dividend trap history</h2>'
        f"{trap}</section></div>"
    )


def _trap_card(entry: CalendarEntry) -> str:
    """Return the body of the trap history card: the last Ex Dates, or why there are none yet."""
    t = entry.trap
    if t is None or not t.events:
        return (
            '<p class="muted">No Ex Date history yet. It is fetched in the background '
            "and appears on the next refresh.</p>"
        )
    rows = "".join(
        f"<tr class='{'neg' if ev.is_trap else ''}'>"
        f"<td>{date_short(ev.ex_date)}</td><td class='r num'>{fmt(ev.dividend, 2)}</td>"
        f"<td class='r num'>{fmt(ev.drop, 1)} ({fmt(ev.drop_pct, 1)}%)</td>"
        f"<td class='r num'>{'—' if ev.recover_days is None else str(ev.recover_days) + ' d'}</td></tr>"
        for ev in t.events
    )
    hits = round((t.trap_rate or 0) * len(t.events))
    summary = (
        f"Price fell more than the dividend in {hits} of {len(t.events)} Ex Dates. "
        f"Median drop {fmt(t.median_drop_pct, 1)}% against a median dividend of "
        f"{fmt(t.median_dividend_pct, 1)}%."
    )
    return (
        '<table class="hd-trap"><thead><tr>'
        f"{th('Ex Date')}{th('Dividend', classes='r')}{th('Drop', classes='r')}"
        f"{th('Back at cum', classes='r')}</tr></thead>"
        f"<tbody>{rows}</tbody></table><p class='muted hd-note'>{escape(summary)}</p>"
    )


def howto_card(open_: bool) -> str:
    """Return the how-to guide as a collapsible card that opens when open_ is true.
    It explains the four dates, the table, the score, the filters and both hunting styles in turn.
    The text is static, so nothing in it needs escaping.
    """
    opened = " open" if open_ else ""
    return f"""<details class="card howto"{opened}>
<summary>How to use this page</summary>
<div class="howto-body">
<h3>What this page is</h3>
<p>A dividend-hunting tool for the market in the header. Every row is one dividend that is announced, being paid, or paid in the last month. The rows are ranked by a hunt score so the most attractive come first. Nothing here is investment advice: it organises data so you can decide faster.</p>
<h3>The four dates</h3>
<ul>
<li><b>Cum Date</b>: the last day you can buy and still get the dividend. Buy on or before it.</li>
<li><b>Ex Date</b>: the first day the stock trades without the dividend. The price usually drops by about the dividend on this day.</li>
<li><b>Recording Date</b>: the day the company records who owns the stock and is entitled to the dividend.</li>
<li><b>Payment Date</b>: the day the money reaches your fund account.</li>
</ul>
<p>The feeds publish the Ex Date and the Payment Date. The Cum Date is worked out as the trading day before the Ex Date, so it is marked <i>est.</i>. The Recording Date is read from the stock feed when it is there and is marked <i>est.</i> when it is worked out as the trading day after the Ex Date. Weekends are skipped but market holidays are not known, so around a holiday an estimated date can be a day or two off. Always confirm on the issuer's announcement before you trade.</p>
<h3>Reading the table</h3>
<ul>
<li><b>Event</b>: this one payment as a percentage of today's price. It is what a single holding earns from this dividend, before any price drop.</li>
<li><b>Yield</b>: the dividend yield over a year.</li>
<li><b>Payout</b>: the share of profit paid out. 30 to 70 percent is healthy; above 90 percent leaves little for growth and is shown in red.</li>
<li><b>Streak</b>: years in a row the company has paid a dividend. Three or more shows a track record.</li>
<li><b>Trap</b>: how often, in the last six Ex Dates, the price fell by more than the dividend. See the trap section below.</li>
<li><b>Score</b>: 0 to 100, higher is better, explained below.</li>
<li><b>Timeline</b>: six weeks from today. The dots are <b>C</b> Cum Date, <b>E</b> Ex Date, <b>R</b> Recording Date and <b>P</b> Payment Date, and the bar covers the time from the first date to the last. A note says when the Ex Date has already passed. Hover a dot for its date.</li>
</ul>
<h3>The hunt score and the style switch</h3>
<p>The score blends yield, payout ratio, consistency, cash-flow cover, liquidity and trap risk. The <b>Style</b> switch changes the weights. <b>Short-term hunter</b> favours a high event yield, low trap risk and good liquidity, because you plan to sell soon after the Ex Date. <b>Long-term income</b> favours the yearly yield, a long streak, a healthy payout and cash-flow cover, because you plan to hold and reinvest. A factor with no data is left out, never counted as zero, and a row with too little data has no score and sits at the bottom.</p>
<h3>Filters</h3>
<p>Each chip narrows the list: event yield of at least 2 percent, payout up to 90 percent, a streak of at least three years, hide stocks with medium or high trap risk, and show dividends already past their Ex Date. A stock with a missing figure does not pass a filter on that figure.</p>
<h3>The detail panel</h3>
<p>Click a row (or press its ticker) to see the four dates, a checklist from the guide with a pass, warn or fail for each point, and the dividend trap history. Missing data shows as n/a and is never treated as a pass.</p>
<h3>The dividend trap</h3>
<p>A trap is when the price falls by more than the dividend you receive, so you end up behind. The history table lists the last Ex Dates: the dividend, how far the price fell (in rupiah and percent) and how many trading days it took to get back to the cum-day price. A red row is a trap event. The summary compares the median drop with the median dividend. Prices move for many reasons, so treat this as a guide: it is built from only a handful of events.</p>
<h3>A short-term hunt, step by step</h3>
<ol>
<li>Choose <b>Short-term hunter</b> and turn on <b>Hide trap risk</b>.</li>
<li>Pick a stock near the top whose Cum Date is still ahead. Check its checklist and trap history.</li>
<li>Buy on or before the Cum Date. Mind the settlement days of the exchange.</li>
<li>Decide before the Ex Date whether you hold through the price drop or sell on the Cum Date or at the open of the Ex Date. The trap history shows how the price usually behaves.</li>
<li>If you hold, the Payment Date is when the cash arrives.</li>
</ol>
<h3>A long-term income hunt</h3>
<ol>
<li>Choose <b>Long-term income</b> and turn on the streak and payout filters.</li>
<li>Prefer a long streak, a payout between 30 and 70 percent, and cash flow that covers the dividend.</li>
<li>Buy and hold across several dividends, and reinvest the payments to grow your holding.</li>
</ol>
<h3>The Month view</h3>
<p>Switch to <b>Month</b> for a calendar of the same dates, Monday to Friday, with the dividends grouped by stage below it. Use the arrows to move between months and Today to come back. Dates that fall on a weekend are listed under the grid.</p>
<h3>Where the data comes from</h3>
<p>Dates, amounts, yield, payout and streak come from TradingView and are cached for about an hour. The Ex Date price history comes from Yahoo Finance for the last five years and is fetched in the background, so the trap column fills in a little after the page opens. If a source is down, the last good data is shown.</p>
</div>
</details>"""
