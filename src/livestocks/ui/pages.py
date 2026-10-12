"""NiceGUI pages: the dashboard at / and the ticker detail at /t/{exchange}/{symbol}.
register() defines both pages on the shared NiceGUI app.
Rendering is delegated to the pure builders in components, chart and financials.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from functools import partial
from html import escape
from typing import Any

from nicegui import app, ui

from livestocks.config import Settings
from livestocks.domain import TickerId, TrackedTicker
from livestocks.services import ForecastService, SuggestionService, TickerView
from livestocks.ui import components as c
from livestocks.ui import suggestions as s
from livestocks.ui.chart import forecast_options
from livestocks.ui.errors import HANDLED, describe
from livestocks.ui.financials import fin_table, financial_options
from livestocks.ui.models import PageState
from livestocks.ui.theme import CSS, FONTS_HEAD


class T(ui.element):
    """A plain HTML element whose inner text can be set with .text.
    NiceGUI's bare ui.element has no text property, so this subclass adds one.
    Used for headings, buttons, table cells and other structural tags.
    """

    @property
    def text(self) -> str:
        """Inner text of the element; assigning it replaces the content.
        Reading returns an empty string when nothing was set.
        The browser escapes it, so it is never parsed as HTML.
        """
        return self._text or ""

    @text.setter
    def text(self, value: str) -> None:
        """Inner text of the element; assigning it replaces the content.
        Reading returns an empty string when nothing was set.
        The browser escapes it, so it is never parsed as HTML.
        """
        self._text = value


SPARK_DAYS = 90
RANGES = {"3M": 90 * 86400, "6M": 180 * 86400, "1Y": 365 * 86400, "2Y": 0}


def register(service: ForecastService, suggestions: SuggestionService, settings: Settings) -> None:
    """Define the dashboard, detail and suggestions pages and bind them to the services.
    Pages read the services on a timer and refresh only when something changed.
    Add, remove and retry actions go through the forecast service, which wakes the updater.
    """

    def tv_url(r: TrackedTicker) -> str:
        return f"https://www.tradingview.com/symbols/{r.exchange}-{r.symbol}/forecast-price-target/"

    # ---- shared shell ----
    async def shell(state: PageState, on_theme: Callable[[], Awaitable[None]]) -> None:
        ui.add_head_html(FONTS_HEAD)
        ui.add_css(CSS)
        dark = ui.dark_mode(state.dark)

        async def toggle() -> None:
            state.dark = not state.dark
            app.storage.user["dark"] = state.dark
            dark.value = state.dark
            await on_theme()

        async def add(e=None) -> None:
            # Read the box in the browser: the server-side value can lag a fast type-then-click.
            raw = await ui.run_javascript("document.querySelector('.add input').value") or ""
            if not raw.strip():
                return
            try:
                result = await service.track(raw)
            except HANDLED as err:
                ui.notify(describe(err), type="negative")
                return
            key = result.ticker.key
            if result.created:
                ui.notify(f"Tracking {key}. Fetching forecast…", type="positive")
            else:
                ui.notify(f"{key} is already tracked", type="info")
            field.value = ""

        with T("header").classes("top"), T("div").classes("wrap"):
            with T("button").classes("brand").on("click", lambda: ui.navigate.to("/")):
                ui.html(
                    '<svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden="true">'
                    '<rect width="30" height="30" rx="8" fill="var(--accent-soft)"/>'
                    '<path d="M6 21l6-7 4 4 8-10" stroke="var(--accent)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
                    '<circle cx="24" cy="8" r="2.3" fill="var(--accent)"/></svg>',
                    sanitize=False,
                )
                ui.html(
                    "<span>LiveStocks<small>Analyst forecasts</small></span>",
                    sanitize=False,
                    tag="span",
                )
            with T("div").classes("add"):
                field = (
                    ui.input(placeholder="Add ticker  ·  TLKM  or  IDX:TLKM")
                    .props('borderless dense input-class="add-input" aria-label="Add ticker"')
                    .classes("add-field")
                    .on("keydown.enter", add)
                )
                T("button").classes("btn").on("click", add).text = "Add"
            if settings.ui_suggestions:
                T("button").classes("btn ghost").on(
                    "click", lambda: ui.navigate.to("/suggestions")
                ).text = "Suggestions"
            with T("div").classes("status").props('aria-live="polite"'):
                dot = T("span").classes("dot")
                status = ui.label()
            with (
                T("button")
                .classes("btn ghost icon")
                .props('aria-label="Toggle theme" title="Toggle theme"')
                .on("click", toggle)
            ):
                ui.html(
                    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
                    'stroke-linecap="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>',
                    sanitize=False,
                )

        async def tick() -> None:
            busy = len(service.fetching())
            dot.classes(add="busy" if busy else "", remove="" if busy else "busy")
            if busy:
                status.text = f"Fetching {busy} ticker{'s' if busy > 1 else ''}…"
            else:
                nxt = await service.seconds_until_next_refresh()
                status.text = "Crawler idle" + (
                    " · no tickers"
                    if nxt is None
                    else " · refresh due"
                    if nxt == 0
                    else f" · next refresh in {c.duration(nxt)}"
                )

        await tick()
        ui.timer(2.0, tick)

    def new_state() -> PageState:
        return PageState(dark=app.storage.user.get("dark", True))

    # ---- dashboard ----
    @ui.page("/")
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

        @ui.refreshable
        async def body() -> None:
            rows = await service.list_tickers()
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

        def sorted_rows(rows: list[TrackedTicker]) -> list[TrackedTicker]:
            keys = {
                "ticker": lambda r: r.symbol,
                "price": lambda r: r.forecast.price or 0,
                "up": lambda r: r.upside if r.upside is not None else -1e9,
                "rating": lambda r: (
                    r.forecast.rating_mark if r.forecast and r.forecast.rating_mark else 99
                ),
                "n": lambda r: r.forecast.n_analysts or 0,
            }
            ok = [r for r in rows if r.forecast]
            rest = [r for r in rows if not r.forecast]
            return sorted(ok, key=keys[state.sort_key], reverse=state.sort_dir < 0) + rest

        async def remove(r: TrackedTicker) -> None:
            await service.remove(r.id)
            ui.notify(f"Removed {r.key}")
            await body.refresh()

        async def retry(r: TrackedTicker) -> None:
            await service.retry(r.id)
            await body.refresh()

        def table(rows: list[TrackedTicker]) -> None:
            def th(label: str, key: str | None = None, right: bool = False) -> None:
                el = T("th").classes("r" if right else "")
                with el:
                    if key:
                        on = state.sort_key == key
                        if on:
                            el.props(
                                f'aria-sort="{"ascending" if state.sort_dir > 0 else "descending"}"'
                            )
                        T("button").on("click", partial(sort_by, key)).text = label + (
                            (" ↑" if state.sort_dir > 0 else " ↓") if on else ""
                        )
                    else:
                        el.text = label

            with T("section").classes("card").props('aria-label="Tracked tickers"'):
                with T("div").classes("card-head"):
                    T("h2").text = "Forecast table"
                    ui.html(
                        '<span><i class="sw px"></i>Price</span><span><i class="sw avg"></i>Avg target</span>'
                        '<span><i class="sw span"></i>Low to high target</span>',
                        sanitize=False,
                    ).classes("legend")
                with T("div").classes("tablewrap").style("margin-top:8px"), T("table"):
                    with T("thead"), T("tr"):
                        th("Ticker", "ticker")
                        th("Price", "price", True)
                        T("th").classes("r").text = "Avg target"
                        th("Upside", "up", True)
                        T("th").text = "Target range"
                        th("Rating", "rating")
                        th("Analysts", "n", True)
                        T("th").text = "Updated"
                        T("th")
                    with T("tbody"):
                        for r in sorted_rows(rows):
                            row_view(r)

        def row_view(r: TrackedTicker) -> None:
            f = r.forecast
            tr = T("tr").on("click", partial(ui.navigate.to, f"/t/{r.exchange}/{r.symbol}"))
            with tr:
                ui.html(c.ticker_cell(r), sanitize=False, tag="td")
                busy = r.key in service.fetching()
                if f is None:
                    if r.status == "failed":
                        msg = f'<td colspan="6" class="err">⚠ {escape(r.last_error or "failed")} · gave up after {r.fail_count} tries</td>'
                    elif r.status == "error":
                        msg = f'<td colspan="6" class="err">⚠ {escape(r.last_error or "error")} · retry {r.fail_count}</td>'
                    else:
                        msg = '<td colspan="6" class="muted"><span class="spin"></span>Fetching first forecast…</td>'
                    ui.html(msg, sanitize=False, tag="td").props('colspan="6"')
                else:
                    ui.html(
                        f'<div class="num">{c.price_fmt(f.price)}</div>{c.change_line(f.change_pct)}',
                        sanitize=False,
                        tag="td",
                    ).classes("r")
                    ui.html(
                        c.price_fmt(f.pt_avg) if f.pt_avg else "—", sanitize=False, tag="td"
                    ).classes("r num")
                    ui.html(c.upside_chip(r.upside), sanitize=False, tag="td").classes("r")
                    ui.html(c.range_bar(f), sanitize=False, tag="td")
                    ui.html(c.rate_pill(f.rating_mark), sanitize=False, tag="td")
                    ui.html(
                        str(f.n_analysts if f.n_analysts is not None else "—"),
                        sanitize=False,
                        tag="td",
                    ).classes("r num")
                ui.html(
                    '<span class="spin"></span>fetching'
                    if busy and f
                    else c.ago(r.fetched_at or r.last_fetch),
                    sanitize=False,
                    tag="td",
                ).classes("muted")
                with T("td").classes("r"):
                    if r.status in ("error", "failed"):
                        T("button").classes("act retry").props(
                            'aria-label="Retry" title="Retry"'
                        ).on("click.stop", partial(retry, r)).text = "↻"
                    T("button").classes("act").props(
                        f'aria-label="Remove {r.symbol}" title="Remove"'
                    ).on("click.stop", partial(remove, r)).text = "✕"

        async def theme_changed() -> None:
            await body.refresh()

        await shell(state, theme_changed)
        with T("div").classes("wrap"), T("main"):
            await body()
        footer()

        async def maybe_refresh() -> None:
            if await sig() != last["sig"]:
                await body.refresh()

        ui.timer(3.0, maybe_refresh)

    # ---- detail ----
    @ui.page("/t/{exchange}/{symbol}")
    async def detail(exchange: str, symbol: str) -> None:
        tid = TickerId(exchange.upper(), symbol.upper())
        state = new_state()
        last: dict[str, Any] = {"sig": None}

        def sig_of(view: TickerView | None) -> tuple[Any, ...] | None:
            return view.signature if view else None

        @ui.refreshable
        async def body() -> None:
            view = await service.get_ticker(tid)
            last["sig"] = sig_of(view)
            r = view.ticker if view else None
            extras = view.extras if view else None
            counts = (
                [n for _, n in extras.rating_counts] if extras and extras.rating_counts else None
            )
            with T("div").classes("crumb"):
                T("button").on("click", lambda: ui.navigate.to("/")).text = "← Dashboard"
                T("span").text = "/"
                T("span").text = tid.key

            if r is None:
                with T("section").classes("card empty"):
                    T("h3").text = "Ticker not tracked"
                    T("p").text = "Add it from the dashboard to start collecting its forecast."
                return
            f = r.forecast
            if f is None:
                with T("section").classes("card empty"):
                    T("h3").text = (
                        "Fetching first forecast"
                        if r.status == "pending"
                        else "No forecast available"
                    )
                    T("p").text = (
                        "The crawler picked this ticker up and will fill the page in a few seconds."
                        if r.status == "pending"
                        else (r.last_error or "Unknown error")
                    )
                return

            chg = (
                f'<span class="chg {"pos" if f.change_pct >= 0 else "neg"}" style="font-size:14px">'
                f"{c.arrow(f.change_pct)} {abs(f.change_pct):.2f}% today</span>"
                if f.change_pct is not None
                else ""
            )
            with T("div").classes("dhead"):
                ui.html(
                    f"<h1>{escape(r.name or r.symbol)}</h1>"
                    f'<div style="margin-top:8px;display:flex;gap:12px;align-items:baseline;flex-wrap:wrap">'
                    f'<span class="big">{c.price_fmt(f.price)}</span><span class="muted">{escape(r.exchange)}:{escape(r.symbol)}</span>{chg}</div>',
                    sanitize=False,
                )
                with T("div").style("display:flex;gap:10px;align-items:center;flex-wrap:wrap"):
                    ui.html(c.rate_pill(f.rating_mark), sanitize=False, tag="span")
                    ui.html(
                        f'<a class="btn ghost" style="text-decoration:none" href="{tv_url(r)}" target="_blank" '
                        f'rel="noopener">Open on TradingView ↗</a>',
                        sanitize=False,
                        tag="span",
                    )

            n = f.n_analysts
            ui.html(
                f'<div class="card"><div class="card-head"><h2>1-year price target</h2>'
                f'<span class="sub">{n if n is not None else "—"} analysts</span></div>'
                f'<div class="card-body">{c.big_range(f)}</div></div>',
                sanitize=False,
            )

            with T("div").classes("dgrid"):
                with T("div").classes("card chartcard"):
                    with T("div").classes("card-head"):
                        T("h2").text = "Price and forecast"
                        with T("div").classes("seg").props('role="group" aria-label="Range"'):
                            for k in RANGES:
                                b = T("button").on("click", partial(set_range, k))
                                b.props(f'aria-pressed="{str(state.range == k).lower()}"').text = k
                    with T("div").classes("card-body chartbody"):
                        since = int(time.time()) - RANGES[state.range] if RANGES[state.range] else 0
                        bars = await service.price_history(tid, since)
                        ui.echart(
                            forecast_options(bars, f, state.dark, int(time.time() * 1000))
                        ).style("height:100%;min-height:380px;width:100%")
                        if len(bars) < 2:
                            T("p").classes("muted").style(
                                "margin:8px 0 0;font-size:12px"
                            ).text = "No price history for this exchange yet; the line fills in as the crawler refreshes."
                with T("div").style("display:grid;gap:12px;align-content:start;min-width:0"):
                    ui.html(
                        f'<div class="card"><div class="card-head"><h2>Consensus</h2>'
                        f'<span class="sub">{f.n_ratings if f.n_ratings is not None else "—"} ratings · 3 months</span></div>'
                        f'<div class="card-body gauge-wrap">{c.gauge(f.rating_mark, counts)}</div></div>',
                        sanitize=False,
                    )
                    ui.html(
                        f'<div class="card"><div class="card-head"><h2>Details</h2></div>'
                        f'<div class="card-body">{c.facts(r)}</div></div>',
                        sanitize=False,
                    )

            if extras is None:
                ui.html(
                    '<div class="card"><div class="card-body muted">EPS, revenue and the analyst rating breakdown '
                    "appear after the next crawl of this ticker.</div></div>",
                    sanitize=False,
                )
            else:
                with T("div").classes("fingrid"):
                    fin_card("EPS", "eps", "eps_period", extras.eps_fy, extras.eps_fq)
                    fin_card("Revenue", "rev", "rev_period", extras.rev_fy, extras.rev_fq)

        async def set_range(k: str) -> None:
            state.range = k
            await body.refresh()

        async def set_period(attr: str, k: str) -> None:
            setattr(state, attr, k)
            await body.refresh()

        def fin_card(title: str, kind: str, attr: str, annual, quarterly) -> None:
            with T("div").classes("card"):
                with T("div").classes("card-head"):
                    T("h2").text = title
                    with T("div").classes("seg").props(f'role="group" aria-label="{title} period"'):
                        for k in ("Annual", "Quarterly"):
                            b = T("button").on("click", partial(set_period, attr, k))
                            b.props(
                                f'aria-pressed="{str(getattr(state, attr) == k).lower()}"'
                            ).text = k
                with T("div").classes("card-body"):
                    periods = annual if getattr(state, attr) == "Annual" else quarterly
                    if not periods:
                        T("p").classes("muted").text = f"No {title.lower()} data for this ticker."
                        return
                    ui.echart(financial_options(periods, kind, state.dark)).style(
                        "height:300px;width:100%"
                    )
                    ui.html(fin_table(periods, kind), sanitize=False)

        await shell(state, body.refresh)
        with T("div").classes("wrap"), T("main"):
            await body()
        footer()

        async def maybe_refresh() -> None:
            if sig_of(await service.get_ticker(tid)) != last["sig"]:
                await body.refresh()

        ui.timer(3.0, maybe_refresh)

    # ---- suggestions ----
    @ui.page("/suggestions")
    async def suggestions_page() -> None:
        state = new_state()
        last: dict[str, Any] = {"sig": None}

        def sig_of(reports: list[Any]) -> tuple[Any, ...]:
            return tuple((r.date, r.received_at) for r in reports)

        async def closes_of(items: list[dict[str, Any]]) -> dict[str, list[float]]:
            exchange = settings.default_exchange.upper()
            since = int(time.time()) - SPARK_DAYS * 86400
            tickers = sorted({str(r["ticker"]) for r in items if r.get("ticker")})
            bars = await asyncio.gather(
                *(service.price_history(TickerId(exchange, t), since) for t in tickers)
            )
            return {t: [b.close for b in bs] for t, bs in zip(tickers, bars, strict=True)}

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

        await shell(state, body.refresh)
        with T("div").classes("wrap"), T("main"):
            await body()
        footer()

        async def maybe_refresh() -> None:
            reports = await suggestions.recent(14) if settings.ui_suggestions else []
            if sig_of(reports) != last["sig"]:
                await body.refresh()

        ui.timer(15.0, maybe_refresh)

    def footer() -> None:
        ui.html(
            "<span>Source: TradingView analyst forecasts. Refreshed every "
            f"{max(1, settings.refresh_interval // 3600)} hours. Not investment advice.</span>",
            sanitize=False,
            tag="footer",
        ).classes("wrap foot")
