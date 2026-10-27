"""NiceGUI main file for page tests: registers every page on fake services and starts nothing."""

from nicegui import ui
from tests.unit.ui.app import fakes

from livestocks.config import Settings
from livestocks.ui.pages import register

register(fakes.FakeForecasts(), fakes.FakeSuggestions(), fakes.FakeCalendar(), Settings())
ui.run(storage_secret="test")
