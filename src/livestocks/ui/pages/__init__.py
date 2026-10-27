"""NiceGUI pages: the dashboard, the ticker detail, the suggestions and the dividend calendar.
Each page lives in its own module; register wires them all to the shared services.
The package keeps the import path ui.pages, so the app wiring did not change.
"""

from livestocks.config import Settings
from livestocks.services import CalendarService, ForecastService, SuggestionService
from livestocks.ui.pages import calendar_page, dashboard, detail, suggestions_page
from livestocks.ui.pages.common import Deps

__all__ = ["register"]


def register(
    service: ForecastService,
    suggestions: SuggestionService,
    calendar: CalendarService,
    settings: Settings,
) -> None:
    """Define every page and bind it to the services.
    Each page receives the same Deps, so the wiring stays in one place.
    Pages register their own routes, so adding a page means adding one module and one line here.
    """
    deps = Deps(service=service, suggestions=suggestions, calendar=calendar, settings=settings)
    dashboard.register(deps)
    detail.register(deps)
    suggestions_page.register(deps)
    calendar_page.register(deps)
