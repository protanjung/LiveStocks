# Configuration

Every setting is read from an environment variable named `LIVESTOCKS_<NAME>`, or from the same name in a `.env`
file in the working directory. The defaults suit a local single-user run. Durations are in seconds.

| Variable | Default | Meaning |
|---|---|---|
| `LIVESTOCKS_DB_PATH` | `data/livestocks.db` | SQLite file. Its folder is created if missing. |
| `LIVESTOCKS_DEFAULT_EXCHANGE` | `IDX` | Exchange assumed when only a symbol is given. |
| `LIVESTOCKS_REFRESH_INTERVAL` | `21600` | How long a ticker's data is considered fresh (6 hours). |
| `LIVESTOCKS_POLL_INTERVAL` | `30` | How often the updater looks for tickers that are due. |
| `LIVESTOCKS_CONCURRENCY` | `2` | Tickers crawled at the same time. |
| `LIVESTOCKS_JITTER_MAX` | `3.0` | Random delay before each crawl, to avoid a burst of identical requests. |
| `LIVESTOCKS_REQUEST_TIMEOUT` | `20.0` | Timeout of one HTTP request to TradingView or Yahoo. |
| `LIVESTOCKS_MAX_FAILURES` | `5` | Failures in a row before a ticker is marked failed and no longer crawled. |
| `LIVESTOCKS_API_WAIT_SECONDS` | `30.0` | How long the API waits for a first crawl before answering 504. |
| `LIVESTOCKS_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING` or `ERROR`. |
| `LIVESTOCKS_LOG_JSON` | `false` | Write one JSON object per log line, for log collectors. |
| `LIVESTOCKS_HOST` | `127.0.0.1` | Address to listen on. Use `0.0.0.0` to accept other devices. |
| `LIVESTOCKS_PORT` | `8080` | Port to listen on. |

NiceGUI keeps per-visitor preferences (such as the theme) in a storage folder. It defaults to `.nicegui` and is moved
with the `NICEGUI_STORAGE_PATH` environment variable. The Docker image sets it to `/data/.nicegui`.

## Failed tickers

A crawl that fails is retried with a growing delay (2, 4, 8 ... minutes, never longer than the refresh interval).
After `LIVESTOCKS_MAX_FAILURES` failures in a row the ticker is marked failed and shown with a retry button; the
retry button, or adding the ticker again from the dashboard, clears the failure state.
