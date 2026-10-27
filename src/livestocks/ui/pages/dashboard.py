"""The dashboard at /: KPI strip, sortable forecast table, suggestion summary and rankings.
Rows refresh on a timer, and the page redraws only when the data or the sort changes.
The table is one HTML string, so the page does not build a widget per cell.
"""

import time
from typing import Any

from nicegui import events, ui

from livestocks.domain import TrackedTicker
from livestocks.ui import components as c
from livestocks.ui import suggestions as s
from livestocks.ui.live import guarded, render_or_notice
from livestocks.ui.pages.common import DASHBOARD_NOTE, Deps, T, footer, new_state, shell
from livestocks.ui.primitives import card

# Runs in the browser: one listener handles sort, retry, remove and row navigation.
TABLE_CLICK_JS = (
    "(e) => {"
    " const act = e.target.closest('[data-act]');"
    " if (act) { emit(act.dataset.act, act.dataset.key); return; }"
    " const row = e.target.closest('tr[data-href]');"
    " if (row) emit('nav', row.dataset.href);"
    "}"
)


def register(deps: Deps) -> None:
    """Define the dashboard page and bind it to the forecast and suggestion services.
    The page reads the services on a timer and refreshes only when something changed.
    Sorting and row actions are handled by one click listener on the table.
    """
    service, settings, suggestions = deps.service, deps.settings, deps.suggestions

    # ---- dashboard ----
    @ui.page("/", title="Dashboard · LiveStocks")
    async def index() -> None:
        state = new_state()

        async def latest_report() -> Any:
            if not settings.ui_suggestions:
                return None
            reports = await suggestions.recent(1)
            return reports[0] if reports else None

        async def sig() -> tuple[Any, ...]:
            rows = await service.list_tickers()
            report = await latest_report()
            return (
                tuple((r.key, r.status, r.fetched_at, r.last_error, r.fail_count) for r in rows),
                (report.date, report.received_at) if report else None,
                tuple(sorted(service.fetching())),
                state.sort_key,
                state.sort_dir,
                state.dark,
                int(time.time() // 60),
            )

        last: dict[str, Any] = {"sig": None}
        rows_by_key: dict[str, TrackedTicker] = {}

        @ui.refreshable
        async def body() -> None:
            rows = await service.list_tickers()
            rows_by_key.clear()
            rows_by_key.update({r.key: r for r in rows})
            last["sig"] = await sig()
            with T("div").classes("page-title"):
                T("h1").text = "Forecast dashboard"
                T("span").classes("sub").text = "Analyst price targets vs. current price"
            report = await latest_report()
            if report:
                ui.html(
                    s.dashboard_card(s.parse_report(report), report.date, report.received_at),
                    sanitize=False,
                )
            if not rows:
                ui.html(c.empty_state(), sanitize=False)
                return
            ui.html(c.kpi_strip(rows), sanitize=False)
            table(rows)
            with T("div").classes("grid2"):
                ui.html(c.rank_card(rows), sanitize=False)
                ui.html(c.dist_card(rows), sanitize=False)

        async def sort_by(key: str) -> None:
            if state.sort_key == key:
                state.sort_dir = -state.sort_dir
            else:
                state.sort_key, state.sort_dir = key, (1 if key == "ticker" else -1)
            await body.refresh()

        async def remove(r: TrackedTicker) -> None:
            await service.remove(r.id)
            ui.notify(f"Removed {r.key}")
            await body.refresh()

        async def retry(r: TrackedTicker) -> None:
            await service.retry(r.id)
            await body.refresh()

        async def on_table(e: events.GenericEventArguments) -> None:
            action, value = e.args[0], e.args[1]
            if action == "sort":
                await sort_by(value)
            elif action == "nav":
                ui.navigate.to(value)
            elif (r := rows_by_key.get(value)) is not None:
                if action == "retry":
                    await retry(r)
                elif action == "remove":
                    await remove(r)

        def table(rows: list[TrackedTicker]) -> None:
            legend = (
                '<div class="card-body"><div class="legend">'
                '<span><i class="sw px"></i>Price</span>'
                '<span><i class="sw avg"></i>Avg target</span>'
                '<span><i class="sw span"></i>Low to high target</span></div></div>'
            )
            table_html = c.forecast_table(
                rows, state.sort_key, state.sort_dir, service.fetching(), int(time.time())
            )
            body_html = f'{legend}<div class="tablewrap mt-8">{table_html}</div>'
            ui.html(
                card("Forecast table", body_html, label="Tracked tickers", padded=False),
                sanitize=False,
            ).on("click", on_table, js_handler=TABLE_CLICK_JS)

        async def theme_changed() -> None:
            await body.refresh()

        await shell(deps, state, theme_changed)
        with T("div").classes("wrap"), T("main"):
            await render_or_notice(body)
        footer(DASHBOARD_NOTE.format(interval=c.interval_text(settings.refresh_interval)))

        async def maybe_refresh() -> None:
            if await sig() != last["sig"]:
                await body.refresh()

        ui.timer(3.0, guarded("dashboard refresh", maybe_refresh))
