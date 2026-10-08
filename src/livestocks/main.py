import logging

from nicegui import app, ui

from .config import Settings, settings as default_settings
from .store import Store
from .ui.pages import register
from .updater import Updater


def create_app(settings: Settings = default_settings) -> None:
    """Wire store, background updater and pages onto the NiceGUI app."""
    store = Store(settings.db_path)
    updater = Updater(store, settings)

    app.on_startup(updater.start)
    app.on_shutdown(updater.stop)
    app.on_shutdown(store.close)
    register(store, updater, settings)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    create_app()
    ui.run(
        host=default_settings.host,
        port=default_settings.port,
        title="LiveStocks",
        favicon="📈",
        dark=True,
        reload=False,
        show=False,
        storage_secret="livestocks-local",
        show_welcome_message=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
