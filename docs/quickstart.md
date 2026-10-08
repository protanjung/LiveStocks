# Quickstart

## Run it locally

You need [uv](https://docs.astral.sh/uv/). It installs the right Python for you.

```bash
uv sync
uv run livestocks
```

Open <http://127.0.0.1:8080>. The table is empty at first: type a ticker such as `TLKM` or `NASDAQ:AAPL` in the box
at the top and press Add. A bare symbol uses the default exchange (`IDX`, see [Configuration](configuration.md)).
The forecast appears after a few seconds.

## Ask the API

```bash
curl http://127.0.0.1:8080/api/v1/forecast/TLKM
```

The first request for a ticker waits for its first crawl (a few seconds) and tracks it from then on, so it also shows
up on the dashboard. Later requests are answered from storage in milliseconds. See [HTTP API](api.md) for the response
and the error codes. Interactive docs are served at <http://127.0.0.1:8080/api/docs>.

## Run it in Docker

```bash
docker compose up --build
```

The container listens on port 8080 and keeps its database in the `livestocks-data` volume, so tracked tickers survive
restarts and rebuilds. Settings are passed as `LIVESTOCKS_*` environment variables in `compose.yaml`.

## Reach it from another device

By default the server only listens on `127.0.0.1`. To open it from a phone on the same network, set
`LIVESTOCKS_HOST=0.0.0.0` and browse to `http://<your-computer-ip>:8080`.

!!! danger "There is no login"
    Anyone who can reach the port can add and remove tickers and call the API. Only expose it on a network you trust.
