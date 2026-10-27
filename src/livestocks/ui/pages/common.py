"""Shared pieces of the NiceGUI pages: the dependency bundle, the top bar, the footer and page state.
Every page is built from the same Deps, so the services are wired in one place.
The helpers here add no page content of their own; each page decides what it shows.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html import escape

from nicegui import app, ui

from livestocks.config import Settings
from livestocks.services import CalendarService, ForecastService, SuggestionService
from livestocks.ui import components as c
from livestocks.ui.errors import HANDLED, describe
from livestocks.ui.live import guarded
from livestocks.ui.models import PageState
from livestocks.ui.theme import FONTS_HEAD, STYLESHEET_HEAD

DASHBOARD_NOTE = (
    "Source: TradingView analyst forecasts. Refreshed every {interval}. Not investment advice."
)


@dataclass(frozen=True, slots=True)
class Deps:
    """The services and settings that every page is built from.
    Pages receive one Deps from register and read only what they need.
    The bundle is frozen, so a page cannot swap a service for the rest of the app.
    """

    service: ForecastService
    suggestions: SuggestionService
    calendar: CalendarService
    settings: Settings


class T(ui.element):
    """A plain HTML element whose inner text can be set with .text.
    NiceGUI's bare ui.element has no text property, so this subclass adds one.
    Used for headings, buttons, table cells and other structural tags.
    """

    @property
    def text(self) -> str:
        """Inner text of the element; assigning it replaces the content.
        Reading returns an empty string when nothing was set.
        The browser escapes it, so it is never parsed as HTML.
        """
        return self._text or ""

    @text.setter
    def text(self, value: str) -> None:
        """Inner text of the element; assigning it replaces the content.
        Reading returns an empty string when nothing was set.
        The browser escapes it, so it is never parsed as HTML.
        """
        self._text = value


# ---- shared shell ----
async def shell(deps: Deps, state: PageState, on_theme: Callable[[], Awaitable[None]]) -> None:
    """Build the top bar shared by every page and start its status timer.
    The theme toggle calls on_theme so the page can redraw its charts in the new palette.
    The add box reads its text in the browser, so a fast type-then-click is not lost.
    """
    service, settings = deps.service, deps.settings
    ui.add_head_html(FONTS_HEAD)
    ui.add_head_html(STYLESHEET_HEAD)
    dark = ui.dark_mode(state.dark)

    async def toggle() -> None:
        state.dark = not state.dark
        app.storage.user["dark"] = state.dark
        dark.value = state.dark
        await on_theme()

    async def add(e=None) -> None:
        # Read the box in the browser: the server-side value can lag a fast type-then-click.
        raw = await ui.run_javascript("document.querySelector('.add input').value") or ""
        if not raw.strip():
            return
        try:
            result = await service.track(raw)
        except HANDLED as err:
            ui.notify(describe(err), type="negative")
            return
        key = result.ticker.key
        if result.created:
            ui.notify(f"Tracking {key}. Fetching forecast…", type="positive")
        else:
            ui.notify(f"{key} is already tracked", type="info")
        field.value = ""

    with T("header").classes("top"), T("div").classes("wrap"):
        with T("button").classes("brand").on("click", lambda: ui.navigate.to("/")):
            ui.html(
                '<svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden="true">'
                '<rect width="30" height="30" rx="8" fill="var(--accent-soft)"/>'
                '<path d="M6 21l6-7 4 4 8-10" stroke="var(--accent)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
                '<circle cx="24" cy="8" r="2.3" fill="var(--accent)"/></svg>',
                sanitize=False,
            )
            ui.html(
                "<span>LiveStocks<small>Analyst forecasts</small></span>",
                sanitize=False,
                tag="span",
            )
        with T("div").classes("add"):
            field = (
                ui.input(placeholder="Add ticker  ·  TLKM  or  IDX:TLKM")
                .props('borderless dense input-class="add-input" aria-label="Add ticker"')
                .classes("add-field")
                .on("keydown.enter", add)
            )
            T("button").classes("btn").on("click", add).text = "Add"
        if settings.ui_suggestions:
            T("button").classes("btn ghost").on(
                "click", lambda: ui.navigate.to("/suggestions")
            ).text = "Suggestions"
        if settings.ui_calendar:
            T("button").classes("btn ghost").on(
                "click", lambda: ui.navigate.to("/calendar")
            ).text = "Calendar"
        with T("div").classes("status").props('aria-live="polite"'):
            dot = T("span").classes("dot")
            status = ui.label()
        with (
            T("button")
            .classes("btn ghost icon")
            .props('aria-label="Toggle theme" title="Toggle theme"')
            .on("click", toggle)
        ):
            ui.html(
                '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
                'stroke-linecap="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>',
                sanitize=False,
            )

    async def tick() -> None:
        busy = len(service.fetching())
        dot.classes(add="busy" if busy else "", remove="" if busy else "busy")
        if busy:
            status.text = f"Fetching {busy} ticker{'s' if busy > 1 else ''}…"
        else:
            nxt = await service.seconds_until_next_refresh()
            status.text = "Crawler idle" + (
                " · no tickers"
                if nxt is None
                else " · refresh due"
                if nxt == 0
                else f" · next refresh in {c.duration(nxt)}"
            )

    await tick()
    ui.timer(2.0, guarded("header status", tick))


def new_state() -> PageState:
    """Return the per-tab view state, starting from the visitor's stored theme.
    A fresh instance is made for each page load, so tabs do not share choices.
    Only the theme is remembered between visits; the table sort resets on each load.
    """
    return PageState(dark=app.storage.user.get("dark", True))


def footer(note: str) -> None:
    """Render the page footer with its source note, escaped.
    Each page passes its own note, so each one states where its data comes from.
    The note is escaped, so a source string cannot inject markup.
    """
    ui.html(f"<span>{escape(note)}</span>", sanitize=False, tag="footer").classes("wrap foot")
