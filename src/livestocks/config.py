"""Runtime configuration loaded from LIVESTOCKS_* environment variables or .env.
One Settings instance is created at import time and passed to the components.
Defaults suit a local single-user run.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings for the database, crawl schedule, crawl limits and server address.
    Every field can be overridden with a LIVESTOCKS_<FIELD> environment variable.
    Intervals and delays are in seconds.
    """

    model_config = SettingsConfigDict(env_prefix="LIVESTOCKS_", env_file=".env", extra="ignore")

    db_path: Path = Path("data/livestocks.db")
    default_exchange: str = "IDX"
    refresh_interval: int = 6 * 3600  # seconds between refreshes of one ticker
    poll_interval: int = 30  # seconds between updater sweeps for due tickers
    concurrency: int = 2
    jitter_max: float = 3.0  # random delay before each fetch, seconds
    request_timeout: float = 20.0
    max_failures: int = (
        5  # consecutive failures before a ticker is marked dead (kept, no longer fetched)
    )
    api_wait_seconds: float = 30.0  # how long the forecast endpoint waits for a first crawl
    log_level: str = "INFO"
    log_json: bool = False  # one JSON object per log line, for log collectors
    host: str = "127.0.0.1"
    port: int = 8080
    ui_suggestions: bool = True  # show the daily suggestions (holdings, lots) in the web UI
    api_token: str | None = None  # bearer token for the suggestion endpoints; unset disables POST
    ui_calendar: bool = True  # show the market dividend calendar page in the web UI
    calendar_ttl: int = 3600  # seconds a fetched dividend calendar is served before refetching


settings = Settings()
