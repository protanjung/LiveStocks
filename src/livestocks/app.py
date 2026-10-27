"""Composition root: builds the object graph and starts the NiceGUI server.
Settings are read once, the store is opened and the updater and pages are wired.
Control then passes to NiceGUI's uvicorn server.
"""

from pathlib import Path

from loguru import logger
from nicegui import app, ui
from nicegui.ui_run import DocsConfig

from livestocks import __version__
from livestocks.api import build_router, build_suggestions_router, register_error_handlers
from livestocks.config import Settings
from livestocks.config import settings as default_settings
from livestocks.logging_config import configure_logging
from livestocks.services import CalendarService, ForecastService, SuggestionService, Updater
from livestocks.storage import Store
from livestocks.ui import register

DEFAULT_SECRET = "livestocks-local"
DOCS = DocsConfig(
    title="LiveStocks API",
    summary="Analyst forecasts crawled from TradingView.",
    description="Request a ticker to start tracking it and read its latest forecast.",
    version=__version__,
    terms_of_service=None,
    contact=None,
    license_info=None,
)


def create_app(settings: Settings = default_settings) -> None:
    """Wire the store, the background updater and the pages onto the NiceGUI app.
    Startup and shutdown hooks start and stop the updater and close the store.
    Call it once before ui.run(); tests may pass their own Settings.
    """
    app.add_static_files("/static", Path(__file__).parent / "ui" / "static")
    store = Store(settings.db_path)
    updater = Updater(store, settings)
    service = ForecastService(store, updater, settings)
    suggestions = SuggestionService(store)
    calendar = CalendarService(settings)

    async def startup() -> None:
        await store.initialize()
        await updater.start()

    async def shutdown() -> None:
        await updater.stop()
        await calendar.close()
        await store.close()

    app.on_startup(startup)
    app.on_shutdown(shutdown)
    register(service, suggestions, calendar, settings)
    app.include_router(build_router(service), prefix="/api/v1")
    app.include_router(build_suggestions_router(suggestions, settings), prefix="/api/v1")
    register_error_handlers(app)
    # NiceGUI keeps URLs that are already set when fastapi_docs is enabled in main().
    app.docs_url, app.redoc_url, app.openapi_url = "/api/docs", "/api/redoc", "/api/openapi.json"


def main() -> None:
    """Configure logging, build the app and run the server until interrupted.
    Host, port and log level come from LIVESTOCKS_* environment variables.
    This is the target of the livestocks console script.
    """
    configure_logging(default_settings.log_level, json=default_settings.log_json)
    if default_settings.host == "0.0.0.0" and default_settings.storage_secret == DEFAULT_SECRET:
        logger.warning(
            "listening on all interfaces with the default storage secret; "
            "set LIVESTOCKS_STORAGE_SECRET"
        )
    create_app()
    ui.run(
        host=default_settings.host,
        port=default_settings.port,
        title="LiveStocks",
        favicon="\U0001f4c8",
        dark=True,
        reload=False,
        show=False,
        storage_secret=default_settings.storage_secret,
        show_welcome_message=False,
        fastapi_docs=DOCS,
    )
