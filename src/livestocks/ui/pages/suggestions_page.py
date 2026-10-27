"""The suggestions page at /suggestions: the daily brief, one card per stock with its price chart.
Reports are read from storage on each refresh, and the price charts use stored history only.
A ticker with no stored history shows a card without a chart rather than failing the page.
"""

import asyncio
import time
from functools import partial
from typing import Any

from nicegui import ui

from livestocks.domain import TickerId
from livestocks.ui import suggestions as s
from livestocks.ui.live import guarded, render_or_notice
from livestocks.ui.pages.common import Deps, T, footer, new_state, shell

SUGGESTIONS_NOTE = (
    "Source: daily suggestions from the scheduled Claude routine. Not investment advice."
)

SPARK_DAYS = 90


def register(deps: Deps) -> None:
    """Define the suggestions page and bind it to the forecast and suggestion services.
    The page refreshes on a timer when a new report arrives.
    Price history is fetched concurrently and a failure for one ticker leaves only its chart empty.
    """
    service, settings, suggestions = deps.service, deps.settings, deps.suggestions

    # ---- suggestions ----
    @ui.page("/suggestions", title="Suggestions · LiveStocks")
    async def suggestions_page() -> None:
        state = new_state()
        last: dict[str, Any] = {"sig": None}

        def sig_of(reports: list[Any]) -> tuple[Any, ...]:
            return tuple((r.date, r.received_at) for r in reports)

        async def closes_of(items: list[dict[str, Any]]) -> dict[str, list[float]]:
            exchange = settings.default_exchange.upper()
            since = int(time.time()) - SPARK_DAYS * 86400
            tickers = sorted({str(r["ticker"]) for r in items if r.get("ticker")})
            results = await asyncio.gather(
                *(service.price_history(TickerId(exchange, t), since) for t in tickers),
                return_exceptions=True,
            )
            closes: dict[str, list[float]] = {}
            for t, result in zip(tickers, results, strict=True):
                # One ticker with no history must not blank the whole suggestions page.
                closes[t] = [] if isinstance(result, BaseException) else [b.close for b in result]
            return closes

        @ui.refreshable
        async def body() -> None:
            reports = await suggestions.recent(14) if settings.ui_suggestions else []
            last["sig"] = sig_of(reports)
            with T("div").classes("crumb"):
                T("button").on("click", lambda: ui.navigate.to("/")).text = "← Dashboard"
                T("span").text = "/"
                T("span").text = "Suggestions"
            with T("div").classes("page-title"):
                T("h1").text = "Daily suggestions"
                T("span").classes("sub").text = "Pre-market brief from the scheduled Claude routine"
            if not reports:
                with T("section").classes("card empty"):
                    T("h3").text = "No suggestions yet"
                    T("p").text = (
                        "Suggestions are turned off for this server."
                        if not settings.ui_suggestions
                        else "The routine delivers a report on weekday mornings. It will appear here."
                    )
                return
            chosen = next((r for r in reports if r.date == state.day), reports[0])
            data = s.parse_report(chosen)
            with T("section").classes("card").props('aria-label="Suggestions"'):
                with T("div").classes("card-head"):
                    T("h2").text = s.day_label(chosen.date)
                    with T("div").classes("seg").props('role="group" aria-label="Trading date"'):
                        for r in reports:
                            b = T("button").on("click", partial(set_day, r.date))
                            b.props(
                                f'aria-pressed="{str(r.date == chosen.date).lower()}"'
                            ).text = s.day_label(r.date)
                ui.html(s.report_head(data, chosen.received_at), sanitize=False)
                items = s.items_of(data)
                ui.html(s.suggestion_cards(items, await closes_of(items)), sanitize=False)
                with T("div").classes("card-body"):
                    ui.html(s.disclaimer(data), sanitize=False)

        async def set_day(day: str) -> None:
            state.day = day
            await body.refresh()

        await shell(deps, state, body.refresh)
        with T("div").classes("wrap"), T("main"):
            await render_or_notice(body)
        footer(SUGGESTIONS_NOTE)

        async def maybe_refresh() -> None:
            reports = await suggestions.recent(14) if settings.ui_suggestions else []
            if sig_of(reports) != last["sig"]:
                await body.refresh()

        ui.timer(15.0, guarded("suggestions refresh", maybe_refresh))
