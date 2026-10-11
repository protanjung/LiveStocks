import pytest

from livestocks.services import SuggestionNotFoundError, SuggestionService


@pytest.fixture
def service(store):
    return SuggestionService(store)


class TestSuggestionService:
    async def test_latest_and_get_fail_clearly_when_nothing_is_stored(self, service):
        with pytest.raises(SuggestionNotFoundError, match="yet"):
            await service.latest()
        with pytest.raises(SuggestionNotFoundError, match="2026-10-12"):
            await service.get("2026-10-12")

    async def test_saved_reports_are_found_by_date_and_as_latest(self, service):
        await service.save("2026-10-09", "t", "friday")
        saved = await service.save("2026-10-12", "t", "monday")

        assert await service.get("2026-10-09") != saved
        assert await service.latest() == saved
        assert [r.date for r in await service.recent(5)] == ["2026-10-12", "2026-10-09"]
