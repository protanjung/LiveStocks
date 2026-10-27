"""The dividend calendar page at /calendar: a month grid or agenda, then the announced and recent dates.
The month shown is kept per tab, so moving between months does not refetch the calendar.
The data source and its limits are stated in the footer.
"""

from datetime import date
from functools import partial
from typing import Any

from nicegui import ui

from livestocks.domain import CalendarEntry
from livestocks.services import CalendarUnavailableError
from livestocks.ui import dividends as dv
from livestocks.ui.errors import describe
from livestocks.ui.live import guarded, render_or_notice
from livestocks.ui.pages.common import Deps, T, footer, new_state, shell
from livestocks.ui.primitives import crumb, empty_card, page_title

CALENDAR_NOTE = (
    "Source: TradingView scanner. Cum Dates are derived from the Ex Date and ignore market holidays; "
    "Recording Dates come from the stock feed where available. Dates can change; check the issuer. "
    "Not investment advice."
)


def register(deps: Deps) -> None:
    """Define the dividend calendar page and bind it to the calendar service.
    The page reloads on a timer, and the date in its signature keeps "today" current at midnight.
    Month navigation changes only the view, so the data is fetched once per refresh.
    """
    calendar, settings = deps.calendar, deps.settings

    # ---- dividend calendar ----
    @ui.page("/calendar", title="Calendar · LiveStocks")
    async def calendar_page() -> None:
        state = new_state()
        last: dict[str, Any] = {"sig": None}
        exchange = settings.default_exchange.upper()

        def sig_of(entries: list[CalendarEntry]) -> tuple[Any, ...]:
            # The date is part of the signature so "today" moves on at midnight without a reload.
            rows = tuple(
                (e.symbol, e.cum_date, e.ex_date, e.record_date, e.pay_date, e.kind)
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

        @ui.refreshable
        async def body() -> None:
            entries, problem = await load()
            last["sig"] = sig_of(entries)
            ui.html(crumb(("← Dashboard", "/"), ("Calendar", None)), sanitize=False)
            ui.html(
                page_title(
                    "Dividend calendar", f"{exchange} · Cum, Ex, Recording and Payment Dates"
                ),
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
            await body.refresh()

        await shell(deps, state, body.refresh)
        with T("div").classes("wrap"), T("main"):
            await render_or_notice(body)
        footer(CALENDAR_NOTE)

        async def maybe_refresh() -> None:
            entries, _ = await load()
            if sig_of(entries) != last["sig"]:
                await body.refresh()

        ui.timer(60.0, guarded("calendar refresh", maybe_refresh))
