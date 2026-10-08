"""NiceGUI pages: the dashboard at / and the ticker detail at /t/{exchange}/{symbol}.
register() defines both pages on the shared NiceGUI app.
Rendering is delegated to the pure builders in components, chart and financials.
"""

import time
from functools import partial
from html import escape
from typing import Any

from nicegui import app, ui

from livestocks.config import Settings
from livestocks.domain import (
    InvalidTickerError,
    PriceBar,
    TrackedTicker,
    parse_ticker,
)
from livestocks.services import Updater
from livestocks.storage import Store
from livestocks.ui import components as c
from livestocks.ui.chart import forecast_options
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


RANGES = {"3M": 90 * 86400, "6M": 180 * 86400, "1Y": 365 * 86400, "2Y": 0}


def register(store: Store, updater: Updater, settings: Settings) -> None:
    """Define the dashboard and detail pages and bind them to the store and updater.
    Pages read the store on a timer and refresh only when something changed.
    Add, remove and retry actions call the store and wake the updater.
    """

    def tv_url(r: TrackedTicker) -> str:
        return f"https://www.tradingview.com/symbols/{r.exchange}-{r.symbol}/forecast-price-target/"

    # ---- shared shell ----
    def shell(state: PageState, on_theme) -> None:
        ui.add_head_html(FONTS_HEAD)
        ui.add_css(CSS)
        dark = ui.dark_mode(state.dark)

        def toggle() -> None:
            state.dark = not state.dark
            app.storage.user["dark"] = state.dark
            dark.value = state.dark
            on_theme()

        async def add(e=None) -> None:
            # Read the box in the browser: the server-side value can lag a fast type-then-click.
            raw = await ui.run_javascript("document.querySelector('.add input').value") or ""
            if not raw.strip():
                return
            try:
                tid = parse_ticker(raw, settings.default_exchange)
            except InvalidTickerError as err:
                ui.notify(str(err), type="negative")
                return
            exchange, symbol = tid.exchange, tid.symbol
            if store.add_ticker(exchange, symbol):
                ui.notify(f"Tracking {exchange}:{symbol}. Fetching forecast…", type="positive")
                updater.wake()
            else:
                store.retry(exchange, symbol)  # re-adding a failed ticker retries it
                updater.wake()
                ui.notify(f"{exchange}:{symbol} is already tracked", type="info")
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

        def tick() -> None:
            busy = len(updater.fetching)
            dot.classes(add="busy" if busy else "", remove="" if busy else "busy")
            if busy:
                status.text = f"Fetching {busy} ticker{'s' if busy > 1 else ''}…"
            else:
                nxt = updater.next_sweep_in()
                status.text = "Crawler idle" + (
                    " · no tickers"
                    if nxt is None
                    else " · refresh due"
                    if nxt == 0
                    else f" · next refresh in {c.duration(nxt)}"
                )

        tick()
        ui.timer(2.0, tick)

    def new_state() -> PageState:
        return PageState(dark=app.storage.user.get("dark", True))

    # ---- dashboard ----
    @ui.page("/")
    def index() -> None:
        state = new_state()

        def sig() -> tuple:
            rows = store.rows()
            return (
                tuple((r.key, r.status, r.fetched_at, r.last_error, r.fail_count) for r in rows),
                tuple(sorted(updater.fetching)),
                state.sort_key,
                state.sort_dir,
                state.dark,
                int(time.time() // 60),
            )

        last: dict[str, Any] = {"sig": None}

        @ui.refreshable
        def body() -> None:
            rows = store.rows()
            last["sig"] = sig()
            with T("div").classes("page-title"):
                T("h1").text = "Forecast dashboard"
                T("span").classes("sub").text = "Analyst price targets vs. current price"
            if not rows:
                ui.html(c.empty_state(), sanitize=False)
                return
            ui.html(c.kpi_strip(rows), sanitize=False)
            table(rows)
            with T("div").classes("grid2"):
                ui.html(c.rank_card(rows), sanitize=False)
                ui.html(c.dist_card(rows), sanitize=False)

        def sort_by(key: str) -> None:
            if state.sort_key == key:
                state.sort_dir = -state.sort_dir
            else:
                state.sort_key, state.sort_dir = key, (1 if key == "ticker" else -1)
            body.refresh()

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

        def remove(r: TrackedTicker) -> None:
            store.remove_ticker(r.exchange, r.symbol)
            ui.notify(f"Removed {r.key}")
            body.refresh()

        def retry(r: TrackedTicker) -> None:
            store.retry(r.exchange, r.symbol)
            updater.wake()
            body.refresh()

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
                busy = r.key in updater.fetching
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

        def theme_changed() -> None:
            body.refresh()

        shell(state, theme_changed)
        with T("div").classes("wrap"), T("main"):
            body()
        footer()

        def maybe_refresh() -> None:
            if sig() != last["sig"]:
                body.refresh()

        ui.timer(3.0, maybe_refresh)

    # ---- detail ----
    @ui.page("/t/{exchange}/{symbol}")
    def detail(exchange: str, symbol: str) -> None:
        exchange, symbol = exchange.upper(), symbol.upper()
        state = new_state()
        last: dict[str, Any] = {"sig": None}

        def sig_of(r: TrackedTicker | None) -> tuple | None:
            ex = store.extras(exchange, symbol)
            return (r.fetched_at, r.status, r.last_error, ex[0] if ex else None) if r else None

        @ui.refreshable
        def body() -> None:
            r = store.row(exchange, symbol)
            last["sig"] = sig_of(r)
            ex = store.extras(exchange, symbol)
            extras = ex[1] if ex else None
            counts = (
                [n for _, n in extras.rating_counts] if extras and extras.rating_counts else None
            )
            with T("div").classes("crumb"):
                T("button").on("click", lambda: ui.navigate.to("/")).text = "← Dashboard"
                T("span").text = "/"
                T("span").text = f"{exchange}:{symbol}"

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
                        bars = store.prices(exchange, symbol, since)
                        if (
                            len(bars) < 2
                        ):  # no price feed for this exchange: fall back to crawl snapshots
                            snaps = [
                                PriceBar(ts, fc.price)
                                for ts, fc in store.history(exchange, symbol, since)
                                if fc.price
                            ]
                            bars = snaps or bars
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

        def set_range(k: str) -> None:
            state.range = k
            body.refresh()

        def set_period(attr: str, k: str) -> None:
            setattr(state, attr, k)
            body.refresh()

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

        shell(state, body.refresh)
        with T("div").classes("wrap"), T("main"):
            body()
        footer()

        def maybe_refresh() -> None:
            r = store.row(exchange, symbol)
            if sig_of(r) != last["sig"]:
                body.refresh()

        ui.timer(3.0, maybe_refresh)

    def footer() -> None:
        ui.html(
            "<span>Source: TradingView analyst forecasts. Refreshed every "
            f"{max(1, settings.refresh_interval // 3600)} hours. Not investment advice.</span>",
            sanitize=False,
            tag="footer",
        ).classes("wrap foot")
