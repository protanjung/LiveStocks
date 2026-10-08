# LiveStocks

Dashboard of analyst price-target forecasts, crawled from TradingView
(e.g. `https://www.tradingview.com/symbols/IDX-TLKM/forecast-price-target/`).

The tracked list starts empty. Add tickers in the UI (`TLKM` or `EXCHANGE:SYMBOL`); a background
crawler fetches each one right away, then refreshes every 6 hours and stores a history of snapshots.

## Run

```
uv run livestocks
```

Open http://127.0.0.1:8080.

## Configuration (env vars, prefix `LIVESTOCKS_`, or `.env`)

| Variable | Default | Meaning |
|---|---|---|
| `DB_PATH` | `data/livestocks.db` | SQLite file |
| `DEFAULT_EXCHANGE` | `IDX` | Exchange used when only a symbol is typed |
| `REFRESH_INTERVAL` | `21600` | Seconds between refreshes of one ticker |
| `POLL_INTERVAL` | `30` | Seconds between updater sweeps |
| `CONCURRENCY` | `2` | Parallel fetches |
| `MAX_FAILURES` | `5` | Consecutive failures before a ticker is marked failed (retry from the UI) |
| `HOST` / `PORT` | `127.0.0.1` / `8080` | Server address |

## How it works

TradingView embeds forecast data as JSON in `<script type="application/prs.init-data+json">` blocks,
so a plain HTTP request is enough (no browser). `scraper.parse_html` locates the blocks by the keys
they contain, because their top-level keys are hashed and change between deploys.

```
src/livestocks/
  scraper.py   fetch + parse (pure parse_html)
  prices.py    daily closes from Yahoo Finance
  store.py     SQLite: tickers, crawl status, forecast history
  updater.py   background loop with concurrency limit, jitter, backoff
  ui/          NiceGUI pages, components, theme
tests/         uv run pytest
```

Price history for the detail chart comes from Yahoo Finance's public chart endpoint (TradingView only serves it
over a websocket). Supported exchanges are listed in `prices.py`; others fall back to the prices saved at each crawl.

Scraping TradingView may conflict with its terms of use; keep it low-volume and personal.
Nothing here is investment advice.
