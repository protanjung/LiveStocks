"""View state for the NiceGUI pages.
Holds the choices a visitor makes: theme, table sort and chart ranges.
Kept separate so pages and tests can share the same dataclass.
"""

from dataclasses import dataclass


@dataclass
class PageState:
    """Per-browser-tab choices: theme, table sort order and chart ranges.
    A fresh instance is created each time a page is opened.
    The theme default comes from the visitor's stored preference.
    """

    dark: bool
    sort_key: str = "up"
    sort_dir: int = -1
    range: str = "1Y"
    eps_period: str = "Annual"
    rev_period: str = "Annual"
    day: str | None = None
    month_offset: int = 0  # months from the current month on the calendar page
    style: str = "short"  # hunting style on the calendar: "short" or "long"
    view: str = "hunt"  # calendar view: "hunt" table or "month" grid
    selected: str | None = None  # EXCHANGE:SYMBOL of the highlighted hunting row
    filters: frozenset[str] = frozenset()  # names of the active hunting filters
    help: bool = False  # whether the how-to guide is open
