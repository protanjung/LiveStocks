"""NiceGUI dashboard: pages, HTML components, charts and theme.
register() wires the pages onto the NiceGUI app.
The helpers in components, chart and financials are pure functions.
"""

from livestocks.ui.pages import register

__all__ = ["register"]
