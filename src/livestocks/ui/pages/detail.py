"""The ticker detail page at /t/{exchange}/{symbol}: price and forecast chart, consensus, dividends and financials.
Charts and tables come from the pure builders; the page only wires them to the services.
Its price and forecast chart can be switched between ranges without leaving the page.
"""

import time
from functools import partial
from html import escape
from typing import Any

from nicegui import ui

from livestocks.domain import TickerId, TrackedTicker
from livestocks.services import TickerView
from livestocks.ui import components as c
from livestocks.ui import dividends as dv
from livestocks.ui.chart import forecast_options
from livestocks.ui.financials import fin_table, financial_options
from livestocks.ui.live import guarded, render_or_notice
from livestocks.ui.pages.common import DASHBOARD_NOTE, Deps, T, footer, new_state, shell
from livestocks.ui.seasonals import seasonal_options, seasonal_returns

RANGES = {"3M": 90 * 86400, "6M": 180 * 86400, "1Y": 365 * 86400, "2Y": 2 * 365 * 86400}


def register(deps: Deps) -> None:
    """Define the ticker detail page and bind it to the forecast service.
    The page reloads its data on a timer and refreshes only when the ticker changed.
    Each card is built from the same view, so the page never mixes old and new data.
    """
    service, settings = deps.service, deps.settings

    def tv_url(r: TrackedTicker) -> str:
        return escape(
            f"https://www.tradingview.com/symbols/{r.exchange}-{r.symbol}/forecast-price-target/"
        )

    # ---- detail ----
    @ui.page("/t/{exchange}/{symbol}", title="Ticker · LiveStocks")
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

            with T("div").classes("card"):
                with T("div").classes("card-head"):
                    T("h2").text = "Seasonals"
                    T("span").classes("sub").text = "10 years · daily % from prior year-end close"
                with T("div").classes("card-body"):
                    history = await service.price_history(tid)
                    if seasonal_returns(history):
                        ui.echart(seasonal_options(history, state.dark)).style(
                            "height:340px;width:100%"
                        )
                    else:
                        T("p").classes("muted").text = "Not enough price history for seasonals yet."

            with T("div").classes("card"):
                with T("div").classes("card-head"):
                    T("h2").text = "Dividends"
                with T("div").classes("card-body"):
                    if extras is None or extras.dividend is None:
                        T("p").classes("muted").text = "No dividend data for this ticker yet."
                    else:
                        ui.html(dv.dividend_card(extras.dividend, int(time.time())), sanitize=False)

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

        await shell(deps, state, body.refresh)
        with T("div").classes("wrap"), T("main"):
            await render_or_notice(body)
        footer(DASHBOARD_NOTE.format(interval=c.interval_text(settings.refresh_interval)))

        async def maybe_refresh() -> None:
            if sig_of(await service.get_ticker(tid)) != last["sig"]:
                await body.refresh()

        ui.timer(3.0, guarded("ticker refresh", maybe_refresh))
