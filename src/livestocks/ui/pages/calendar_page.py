"""The dividend hunting page at /calendar: dividends ranked by hunt score, or a month calendar.
The hunt view ranks every dividend, draws its four dates on a timeline and explains it in a detail panel.
A how-to guide on the page explains the dates, the score, the filters and both hunting styles.
"""

from datetime import date
from functools import partial
from typing import Any

from nicegui import events, ui

from livestocks.domain import CalendarEntry, HuntStyle
from livestocks.services import CalendarUnavailableError
from livestocks.ui import dividends as dv
from livestocks.ui import hunter
from livestocks.ui.errors import describe
from livestocks.ui.live import guarded, render_or_notice
from livestocks.ui.pages.common import TABLE_CLICK_JS, Deps, T, footer, new_state, shell
from livestocks.ui.primitives import card, crumb, empty_card, page_title

CALENDAR_NOTE = (
    "Source: TradingView scanner for dates and fundamentals, Yahoo Finance for Ex Date history. "
    "Cum Dates are derived from the Ex Date and ignore market holidays; Recording Dates come from "
    "the stock feed where available. Dates can change; check the issuer. Not investment advice."
)


def register(deps: Deps) -> None:
    """Define the dividend hunting page and bind it to the calendar service.
    The page is split in two: a header that rebuilds rarely, and a workspace that holds the controls,
    table and detail. Clicks rebuild only the workspace, so the scroll position is kept.
    """
    calendar, settings = deps.calendar, deps.settings

    # ---- dividend hunting ----
    @ui.page("/calendar", title="Calendar · LiveStocks")
    async def calendar_page() -> None:
        state = new_state()
        last: dict[str, Any] = {"sig": None}
        current: dict[str, Any] = {"entries": []}
        exchange = settings.default_exchange.upper()

        def sig_of(entries: list[CalendarEntry]) -> tuple[Any, ...]:
            # The date is part of the signature so "today" moves on at midnight without a reload.
            rows = tuple(
                (
                    e.symbol,
                    e.cum_date,
                    e.ex_date,
                    e.record_date,
                    e.pay_date,
                    e.kind,
                    e.price,
                    e.trap.level if e.trap else None,
                )
                for e in entries
            )
            return (date.today().isoformat(), rows)

        async def load() -> tuple[list[CalendarEntry], str | None]:
            if not settings.ui_calendar:
                return [], None
            try:
                return await calendar.entries(exchange), None
            except CalendarUnavailableError as e:
                return [], describe(e)

        async def on_click(e: events.GenericEventArguments) -> None:
            if hunter.apply_action(state, e.args[0], e.args[1]):
                await workspace.refresh()

        def clickable(html: str) -> None:
            ui.html(html, sanitize=False).on("click", on_click, js_handler=TABLE_CLICK_JS)

        @ui.refreshable
        async def workspace() -> None:
            entries = current["entries"]
            style = HuntStyle(state.style)
            clickable(hunter.controls(style, state.view, state.filters, state.help))
            if state.view == "month":
                month_view(entries)
            else:
                hunt_view(entries, style)
            clickable(hunter.howto_card(state.help))

        @ui.refreshable
        async def body() -> None:
            entries, problem = await load()
            current["entries"] = entries
            last["sig"] = sig_of(entries)
            ui.html(crumb(("← Dashboard", "/"), ("Calendar", None)), sanitize=False)
            ui.html(
                page_title("Dividend hunter", f"{exchange} · ranked by hunt score"),
                sanitize=False,
            )
            if not settings.ui_calendar:
                ui.html(
                    empty_card(
                        "Calendar is turned off",
                        "The dividend calendar is disabled for this server.",
                    ),
                    sanitize=False,
                )
                return
            if problem is not None:
                ui.html(empty_card("Calendar unavailable", problem), sanitize=False)
                return
            await workspace()

        def hunt_view(entries: list[CalendarEntry], style: HuntStyle) -> None:
            rows = hunter.ranked(entries, style, state.filters)
            keys = [hunter.key_of(e) for e, _ in rows]
            if state.selected not in keys:
                state.selected = keys[0] if keys else None
            table = hunter.hunt_table(rows, state.selected, date.today())
            label = "Short-term hunter" if style is HuntStyle.SHORT else "Long-term income"
            clickable(
                card(
                    "Ranked by hunt score",
                    table,
                    sub=f"{len(rows)} dividends · {label}",
                    label="Dividends ranked by hunt score",
                    padded=False,
                )
            )
            chosen = next((e for e, _ in rows if hunter.key_of(e) == state.selected), None)
            if chosen is not None:
                clickable(hunter.hunt_detail(chosen, style))

        def month_view(entries: list[CalendarEntry]) -> None:
            year, month = dv.month_of(date.today(), state.month_offset)
            with T("section").classes("card"):
                with T("div").classes("card-head"):
                    T("h2").text = dv.month_label(year, month)
                    with T("div").style("display:flex;gap:8px"):
                        T("button").classes("btn ghost").on(
                            "click", partial(shift_month, -1)
                        ).text = "‹"
                        if state.month_offset:
                            T("button").classes("btn ghost").on(
                                "click", partial(shift_month, -state.month_offset)
                            ).text = "Today"
                        T("button").classes("btn ghost").on(
                            "click", partial(shift_month, 1)
                        ).text = "›"
                with T("div").classes("card-body"):
                    ui.html(dv.month_grid(entries, year, month, date.today()), sanitize=False)
            sections = dv.calendar_sections(entries)
            if not sections:
                ui.html(
                    empty_card(
                        "No dividends to show",
                        f"No Cum, Ex, Recording or Payment Date in the last month on {exchange}.",
                    ),
                    sanitize=False,
                )
                return
            ui.html(sections, sanitize=False)

        async def shift_month(step: int) -> None:
            state.month_offset += step
            await workspace.refresh()

        await shell(deps, state, body.refresh)
        with T("div").classes("wrap"), T("main"):
            await render_or_notice(body)
        footer(CALENDAR_NOTE)

        async def maybe_refresh() -> None:
            entries, _ = await load()
            if sig_of(entries) != last["sig"]:
                last["sig"] = sig_of(entries)
                current["entries"] = entries
                await workspace.refresh()

        ui.timer(60.0, guarded("calendar refresh", maybe_refresh))
