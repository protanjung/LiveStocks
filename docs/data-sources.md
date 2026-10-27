# Data sources

Nothing here is an official API. Each source is a public page or feed that works today and may change without notice,
so the crawler is written to fail loudly and keep the rest of the system running.

## TradingView forecast page

`https://www.tradingview.com/symbols/{EXCHANGE}-{SYMBOL}/forecast-price-target/`

A plain HTTP request is enough; no browser is needed. The page embeds its data as JSON in
`<script type="application/prs.init-data+json">` blocks. The top-level keys of those blocks are hashed and change
between deployments, so the parser finds data by the keys it contains (`initForecastQuotes`, `symbolFaqData`) and never
by the hashed name.

It provides the last price, the daily change, the all-time high, the average, high and low price target, the analyst
count, the consensus score and the next earnings date.

A 404 means the ticker does not exist (`NotFoundError`). A page that loads but lacks the expected blocks raises
`ParseError`, which almost always means TradingView changed its layout.

## TradingView quote websocket

`wss://data.tradingview.com/socket.io/websocket`

The EPS and revenue charts and the number of analysts per rating are loaded by the page's JavaScript over a websocket,
so they are not in the HTML. An anonymous session (`unauthorized_user_token`) can create a quote session for a symbol and
receive every field, around 1,400 of them, ending with a `quote_completed` message. The crawler reads these fields:

| Field | Meaning |
|---|---|
| `recommendation_buy`, `_over`, `_hold`, `_under`, `_sell` | Analysts rating strong buy, buy, hold, sell, strong sell |
| `earnings_fy_h`, `earnings_fq_h` | EPS per fiscal year and quarter, actual and estimate |
| `revenues_fy_h`, `revenues_fq_h` | Revenue per fiscal year and quarter, actual and estimate |
| `dividend_ex_date_upcoming`, `dividend_payment_date_upcoming`, `dividend_amount_upcoming` | Announced dividend: Ex Date, Payment Date and amount per share. Absent unless one is announced |
| `dividend_ex_date_recent`, `dividend_payment_date_recent`, `dividend_amount_recent` | The most recent dividend |
| `dividend_ex_date_h`, `dividend_payment_date_h`, `dividend_amount_h`, `dividend_type_h`, `dividend_record_date_h` | Dividend history, newest first, index-aligned; index 0 matches the upcoming dividend when one exists. `dividend_record_date_h` is the Recording Date |
| `dividends_yield_current` | Current dividend yield in percent |

This crawl is best-effort. If it fails the forecast is still stored and the dashboard and API show the missing parts as
empty until the next refresh.

## TradingView scanner (dividend calendar)

`POST https://scanner.tradingview.com/{market}/scan` with a JSON filter and column list, no authentication. The market
name comes from a table in `crawler/dividend_calendar.py`; IDX is `indonesia`. Two requests per exchange run each
time the calendar cache expires: announced ex-dates still ahead, and ex-dates from the last 30 days. Rows are merged
by symbol. Announced dividends are sparse on IDX (a handful at a time), so the calendar also lists recent Ex Dates
and Payment Dates still ahead.

The scanner has no Recording Date column, and no field for the Cum Date exists anywhere in the feeds. The Cum Date is
derived as the trading day before the Ex Date, and the Recording Date as the trading day after it, both skipping
weekends only (no market holiday calendar is kept). The real Recording Date is then read per symbol from the quote
websocket (`dividend_record_date_h`, five sessions at a time, about one second each), and replaces the derived one
when the feed has a matching Ex Date. The endpoint is unofficial, like the other sources here.

## Yahoo Finance

`https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=10y&interval=1d`

TradingView only serves price history over the same websocket in a heavier protocol, so daily closes come from Yahoo's
public chart endpoint. A table in `crawler/price_history.py` maps TradingView exchanges to Yahoo suffixes (`IDX` becomes
`.JK`, US exchanges need none). Tickers on an exchange that is not in the table get no history; the price chart then
falls back to the prices saved with each forecast.

## When something breaks

- Check the log: `ParseError` or repeated `UpstreamError` lines name the ticker and the step that failed.
- The test suite parses saved copies of a real TradingView page and quote feed (`tests/fixtures/`). To update them after
  a layout change, save a fresh page and quote dump there, then fix the parser until the tests pass again.
- A ticker that keeps failing is marked failed after `LIVESTOCKS_MAX_FAILURES` attempts and stops generating traffic.
