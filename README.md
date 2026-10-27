# LiveStocks

Analyst forecast dashboard and HTTP API, fed by a background crawler of [TradingView](https://www.tradingview.com).

Track a ticker once and LiveStocks keeps its price targets, analyst consensus, EPS and revenue estimates and price
history fresh. Look at them on a dashboard, or fetch them as JSON.

## Run

```bash
uv sync
uv run livestocks          # http://127.0.0.1:8080
```

Add tickers in the box at the top (`TLKM`, `NASDAQ:AAPL`). The list starts empty.

With Docker:

```bash
docker compose up --build  # data lives in the livestocks-data volume
```

## API

```bash
curl http://127.0.0.1:8080/api/v1/forecast/TLKM
```

`GET /api/v1/forecast/{ticker}` tracks the ticker if it is new, waits for its first crawl (up to 30 seconds), and
returns its forecast. Known tickers are answered from storage at once. Errors use a `{code, detail}` body: `404`
unknown ticker, `422` malformed ticker, `502` upstream failure, `504` first crawl too slow. Interactive docs are at
`/api/docs`.

The scheduled Claude routine "Daily IDX Stock Suggestions" delivers its JSON report with
`POST /api/v1/suggestions`; read it back with `GET /api/v1/suggestions/latest`, `/suggestions/{date}` or
`/suggestions` (history). All of them use `Authorization: Bearer $LIVESTOCKS_API_TOKEN`; without that variable
delivery is disabled. The newest report also shows on the dashboard and at `/suggestions`; the web UI has no login,
so set `LIVESTOCKS_UI_SUGGESTIONS=false` on a public host. See the API page of the documentation.
The stock detail page shows the next dividend with its Cum Date, Ex Date, Recording Date and Payment Date.
`/calendar` is a dividend-hunting tool: it ranks the market's dividends by a hunt score (yield, payout ratio,
consistency, cash-flow cover, liquidity and dividend-trap risk), draws each stock's four dates on a six-week timeline,
shows a pass/warn/fail checklist and the price behaviour on its last Ex Dates, and has a Short-term / Long-term style
switch, filters, a Month view, and a how-to guide on the page. Turn it off with `LIVESTOCKS_UI_CALENDAR=false`.
The `/suggestions` page shows a 90-day price chart on each stock card with its entry, stop and TP1 levels. Charts
use the stored price history, so a stock only gets one after you track it (for example `IDX:BBRI`).

## Configuration

Environment variables prefixed `LIVESTOCKS_` (or a `.env` file), for example `LIVESTOCKS_PORT`,
`LIVESTOCKS_REFRESH_INTERVAL` and `LIVESTOCKS_HOST`. The full list is in the documentation.

There is **no login**. Setting `LIVESTOCKS_HOST=0.0.0.0` lets anyone on your network add tickers and call the API.

## Documentation

```bash
uv sync --group docs
uv run mkdocs serve
```

The site covers the architecture, configuration, the API, the data sources and how to develop the project.

## Development

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pre-commit install
```

Code lives in `src/livestocks/` as `domain`, `crawler`, `storage`, `services`, `api` and `ui` subsystems that depend on
each other in one direction only; `tests/` mirrors that layout.

Scraping TradingView may conflict with its terms of use, so keep it low-volume and personal. Nothing here is
investment advice.
