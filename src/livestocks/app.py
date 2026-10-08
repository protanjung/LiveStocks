"""Composition root: builds the object graph and starts the NiceGUI server.
Settings are read once, the store is opened and the updater and pages are wired.
Control then passes to NiceGUI's uvicorn server.
"""

from nicegui import app, ui

from livestocks.config import Settings
from livestocks.config import settings as default_settings
from livestocks.logging_config import configure_logging
from livestocks.services import Updater
from livestocks.storage import Store
from livestocks.ui import register


def create_app(settings: Settings = default_settings) -> None:
    """Wire the store, the background updater and the pages onto the NiceGUI app.
    Startup and shutdown hooks start and stop the updater and close the store.
    Call it once before ui.run(); tests may pass their own Settings.
    """
    store = Store(settings.db_path)
    updater = Updater(store, settings)

    app.on_startup(updater.start)
    app.on_shutdown(updater.stop)
    app.on_shutdown(store.close)
    register(store, updater, settings)


def main() -> None:
    """Configure logging, build the app and run the server until interrupted.
    Host, port and log level come from LIVESTOCKS_* environment variables.
    This is the target of the livestocks console script.
    """
    configure_logging(default_settings.log_level)
    create_app()
    ui.run(
        host=default_settings.host,
        port=default_settings.port,
        title="LiveStocks",
        favicon="\U0001f4c8",
        dark=True,
        reload=False,
        show=False,
        storage_secret="livestocks-local",
        show_welcome_message=False,
    )
