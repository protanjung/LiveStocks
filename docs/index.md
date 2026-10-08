# LiveStocks

LiveStocks tracks the tickers you care about and keeps their analyst forecasts fresh. It crawls
[TradingView](https://www.tradingview.com) in the background and offers the result in two ways:

- a **dashboard** (NiceGUI) with a sortable forecast table, price-target ranges, a price chart with the
  forecast cone, the analyst consensus gauge and EPS and revenue charts;
- an **HTTP endpoint** that takes a ticker, starts tracking it if it is new, and returns its forecast as JSON.

The tracked list starts empty. A ticker is added from the dashboard or by asking the API for it, and from then on
the crawler refreshes it every six hours and keeps the history in SQLite.

## What you get per ticker

| Data | Source |
|---|---|
| Last price, daily change, all-time high | TradingView forecast page |
| Average, high and low 1-year price target, analyst count | TradingView forecast page |
| Consensus score and the number of analysts per rating | TradingView quote websocket |
| EPS and revenue, annual and quarterly, actual versus estimate | TradingView quote websocket |
| Daily price history | Yahoo Finance |

See [Data sources](data-sources.md) for why three sources are needed and how fragile each one is.

## Where to go next

- [Quickstart](quickstart.md): run it locally or in Docker and make your first request.
- [HTTP API](api.md): the endpoint, its status codes and examples.
- [Architecture](architecture.md): how the code is organised and why.
- [Development](development.md): tooling, code style and how to extend the project.

!!! warning "Not investment advice"
    The data is scraped from public pages and may be late, wrong or disappear. Scraping may also conflict with
    TradingView's terms of use, so keep the request volume low and the use personal.
