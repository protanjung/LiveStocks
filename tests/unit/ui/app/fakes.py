"""Stand-in services for rendering the pages in tests.
The entries the calendar shows are set in ENTRIES before a page is opened."""

from livestocks.domain import CalendarEntry

ENTRIES: list[CalendarEntry] = []
FAIL = {"calendar": False}


class FakeForecasts:
    """Just enough of the forecast service for the page shell."""

    def fetching(self) -> frozenset[str]:
        return frozenset()

    async def seconds_until_next_refresh(self) -> int | None:
        return None

    async def list_tickers(self) -> list:
        return []


class FakeSuggestions:
    """A suggestion service with nothing delivered."""

    async def recent(self, limit: int) -> list:
        return []


class FakeCalendar:
    """A calendar service that returns ENTRIES, or fails when FAIL['calendar'] is set."""

    async def entries(self, exchange: str) -> list[CalendarEntry]:
        from livestocks.services import CalendarUnavailableError

        if FAIL["calendar"]:
            raise CalendarUnavailableError("the dividend calendar is unavailable right now")
        return list(ENTRIES)
