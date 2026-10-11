"""Stores and serves the daily stock suggestion reports delivered by the scheduled routine.
It is the entry point the api layer uses, so routes never touch the store directly.
Payloads arrive already validated; the service keeps them as JSON text.
"""

from livestocks.domain import SuggestionReport
from livestocks.services.errors import SuggestionNotFoundError
from livestocks.storage import Store


class SuggestionService:
    """Save, look up and list the daily suggestion reports.
    One report is kept per trading date, so delivering a date again replaces it.
    Reads are cheap enough to call on every request.
    """

    def __init__(self, store: Store):
        """Create the service over an open store."""
        self._store = store

    async def save(self, date: str, generated_at: str, payload: str) -> SuggestionReport:
        """Store the report of a trading date and return it as stored.
        An earlier report for the same date is replaced.
        payload is the validated JSON text.
        """
        return await self._store.save_suggestions(date, generated_at, payload)

    async def latest(self) -> SuggestionReport:
        """Return the report with the newest trading date.
        Raises SuggestionNotFoundError when none has been delivered yet.
        The date decides, not the time of arrival.
        """
        report = await self._store.latest_suggestions()
        if report is None:
            raise SuggestionNotFoundError("no suggestions have been delivered yet")
        return report

    async def get(self, date: str) -> SuggestionReport:
        """Return the report of one trading date (YYYY-MM-DD).
        Raises SuggestionNotFoundError when that date has none.
        Weekends and holidays have no report.
        """
        report = await self._store.suggestions_on(date)
        if report is None:
            raise SuggestionNotFoundError(f"no suggestions for {date}")
        return report

    async def recent(self, limit: int) -> list[SuggestionReport]:
        """Return up to limit reports, newest trading date first.
        An empty list means nothing has been delivered yet.
        Each report carries its full payload.
        """
        return await self._store.recent_suggestions(limit)
