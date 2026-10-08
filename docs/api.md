# HTTP API

The API has one endpoint. Interactive documentation (Swagger UI) is served at `/api/docs`, ReDoc at `/api/redoc` and the
raw OpenAPI document at `/api/openapi.json`.

## `GET /api/v1/forecast/{ticker}`

Returns the stored analyst forecast for a ticker, tracking it first if it is new.

`{ticker}` is a symbol such as `TLKM`, which uses the default exchange, or `EXCHANGE:SYMBOL` such as `NASDAQ:AAPL`.
Letter case does not matter.

| Situation | Behaviour |
|---|---|
| The ticker is not tracked yet | It is added and the request waits for its first crawl, up to `LIVESTOCKS_API_WAIT_SECONDS`. |
| The ticker is tracked and has data | The stored data is returned at once. `stale` is `true` when it is older than twice the refresh interval. |
| The ticker is tracked but its first crawl is still running | The request waits for that crawl. |
| The ticker is tracked and its last crawl failed | The error is returned at once; the updater retries on its own schedule. |

!!! note "A GET that changes state"
    Asking for an unknown ticker starts tracking it, which means the server starts crawling TradingView for it. Link
    previews, browser prefetching or a scanner hitting URLs can therefore add tickers. Do not expose the API publicly.

### Example

```bash
curl http://127.0.0.1:8080/api/v1/forecast/TLKM
```

```json
{
  "ticker": {"exchange": "IDX", "symbol": "TLKM", "name": "PT Telkom Indonesia (Persero) Tbk Class B"},
  "status": "ok",
  "created": true,
  "fetched_at": "2026-10-08T04:53:01Z",
  "stale": false,
  "price": {"last": 2310.0, "change_pct": 1.32, "all_time_high": 4850.0},
  "price_target": {"average": 3394.09, "high": 4150.0, "low": 2300.0, "upside_pct": 46.93, "analysts": 22},
  "rating": {
    "score": 1.22,
    "label": "Strong buy",
    "total": 23,
    "counts": {"strong_buy": 18, "buy": 2, "hold": 2, "sell": 0, "strong_sell": 1}
  },
  "next_earnings": "2026-10-29T12:00:00Z",
  "estimates": {
    "eps": {
      "annual": [{"period": "2025", "reported": true, "actual": 179.84, "estimate": 214.36, "surprise_pct": -16.1}],
      "quarterly": []
    },
    "revenue": {"annual": [], "quarterly": []}
  }
}
```

(The lists are shortened here; each holds up to 11 annual and 16 quarterly periods, including future estimates.)

Notes on the fields:

- Percentages are plain numbers in percent: `upside_pct: 46.93` means 46.93%.
- `rating.score` runs from 1 (strong buy) to 5 (strong sell).
- `rating.counts` and `estimates` come from a second, best-effort crawl and are `null` when it failed; they fill in
  on the next refresh.
- `fetched_at` and `next_earnings` are UTC timestamps in ISO 8601.

### Errors

Every error has the same body, `{"code": "...", "detail": "..."}`. Branch on `code`; `detail` is for people and may
change.

| Status | `code` | Meaning |
|---|---|---|
| 404 | `ticker_not_found` | TradingView has no such ticker. Retrying will not help. |
| 422 | `invalid_ticker` | The text is not a valid ticker. |
| 502 | `upstream_error` | TradingView or the network failed, or the page layout changed. Usually transient. |
| 504 | `crawl_timeout` | The first crawl did not finish within the wait limit. It keeps running; ask again shortly. |
