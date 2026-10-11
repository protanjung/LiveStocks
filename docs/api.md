# HTTP API

The API has a forecast endpoint and a set of [stock suggestion](#stock-suggestions) endpoints. Interactive documentation (Swagger UI) is served at `/api/docs`, ReDoc at `/api/redoc` and the
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
    previews, browser prefetching or a scanner hitting URLs can therefore add tickers. This endpoint has no login, so
    do not expose it publicly without a reverse proxy that restricts it. Only the suggestion endpoints use a token.

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

## Stock suggestions

A scheduled Claude routine ("Daily IDX Stock Suggestions", weekdays 08:50 Asia/Jakarta) writes a pre-market brief and
ends it with one JSON document of schema `idx-suggestions/v1`. It delivers that document here, and the app keeps one
report per trading date.

All suggestion endpoints use a bearer token, set on the server with `LIVESTOCKS_API_TOKEN`:

```
Authorization: Bearer <LIVESTOCKS_API_TOKEN>
```

Without that variable, delivering is disabled (`503 ingest_disabled`) and reading is open, which suits a local run.
The reports contain your holdings and lot counts, so always set the token on a public host.

| Method and path | Purpose |
|---|---|
| `POST /api/v1/suggestions` | Store a report (`201`). A second report for the same `date` replaces the first. |
| `GET /api/v1/suggestions/latest` | The report with the newest trading date. |
| `GET /api/v1/suggestions/{date}` | The report of one date, `YYYY-MM-DD`. |
| `GET /api/v1/suggestions?limit=30` | History, newest first: date, IHSG, summary and the number of BUY, SELL and HOLD rows. |

### Example

```bash
curl -X POST https://livestocks.example/api/v1/suggestions \
  -H "Authorization: Bearer $LIVESTOCKS_API_TOKEN" -H "Content-Type: application/json" \
  --data @brief.json

curl -H "Authorization: Bearer $LIVESTOCKS_API_TOKEN" https://livestocks.example/api/v1/suggestions/latest
```

```json
{
  "schema": "idx-suggestions/v1",
  "date": "2026-10-12",
  "generated_at": "2026-10-12T08:55:00+07:00",
  "received_at": "2026-10-12T01:55:04Z",
  "market": {"ihsg_last": 6093.75, "summary": "IHSG +1.04% to 6,093.75."},
  "suggestions": [
    {
      "ticker": "BBRI", "name": "Bank Rakyat Indonesia Tbk", "held": true,
      "action": "BUY", "lots": 3,
      "reference_price": 3100, "reference_source": "search",
      "entry": {"low": 3070, "high": 3100, "price": 3090},
      "tp1": 3600, "tp2": 3850, "stop": 2990, "stop_pct": -3.2, "rr": 5.1,
      "post_trade_weight_pct": 12.4, "verified": true, "reason": "Below consensus target.",
      "auto_order": {"side": "BUY", "stock": "BBRI", "start_date": "2026-10-12", "end_date": "2026-10-12",
                     "condition": {"type": "price", "operator": "<=", "value": 3090},
                     "execute": {"by": "price", "price": 3090}, "qty_lots": 3},
      "exits": []
    }
  ],
  "disclaimer": "Informational only, not financial advice."
}
```

(`exits` lists the follow-up TP1 and STOP sell orders of a verified BUY and is left empty here; `received_at` is added
by the server.) Rules of the document:

- `action` is exactly `BUY`, `SELL` or `HOLD`; `lots` is 0 for HOLD.
- Prices are whole rupiah on valid IDX ticks; `stop_pct` is the negative percent from `entry.price`.
- Levels are `null` and `verified` is `false` when the sources did not support them.
- `auto_order` and `exits` describe orders for the Growin' PRO auto order form. They are only suggestions; nothing is
  placed for you.

### Suggestion errors

| Status | `code` | Meaning |
|---|---|---|
| 401 | `unauthorized` | The bearer token is missing or wrong. |
| 404 | `suggestion_not_found` | No report for that date, or none delivered yet. |
| 422 | `invalid_payload` | The body is not a valid `idx-suggestions/v1`; `detail` names the first problems. |
| 422 | `invalid_date` | The date in the URL is not `YYYY-MM-DD`. |
| 503 | `ingest_disabled` | The server has no `LIVESTOCKS_API_TOKEN`. |
