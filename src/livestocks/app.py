"""Composition root: builds the object graph and starts the NiceGUI server."""

from nicegui import app, ui

from livestocks.config import Settings
from livestocks.config import settings as default_settings
from livestocks.logging_config import configure_logging
from livestocks.services import Updater
from livestocks.storage import Store
from livestocks.ui import register


def create_app(settings: Settings = default_settings) -> None:
    """Wire store, background updater and pages onto the NiceGUI app."""
    store = Store(settings.db_path)
    updater = Updater(store, settings)

    app.on_startup(updater.start)
    app.on_shutdown(updater.stop)
    app.on_shutdown(store.close)
    register(store, updater, settings)


def main() -> None:
    """Configure logging, build the app and run the server until interrupted."""
    configure_logging(default_settings.log_level)
    create_app()
    ui.run(
        host=default_settings.host,
        port=default_settings.port,
        title="LiveStocks",
        favicon="\U0001F4C8",
        dark=True,
        reload=False,
        show=False,
        storage_secret="livestocks-local",
        show_welcome_message=False,
    )
