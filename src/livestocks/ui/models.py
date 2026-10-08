"""View state for the NiceGUI pages."""

from dataclasses import dataclass


@dataclass
class PageState:
    """Per-browser-tab choices: theme, table sort, chart ranges."""

    dark: bool
    sort_key: str = "up"
    sort_dir: int = -1
    range: str = "1Y"
    eps_period: str = "Annual"
    rev_period: str = "Annual"
