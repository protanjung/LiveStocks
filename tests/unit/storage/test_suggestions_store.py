class TestSuggestionReports:
    async def test_nothing_stored_means_no_latest_and_no_date(self, store):
        assert await store.latest_suggestions() is None
        assert await store.suggestions_on("2026-10-12") is None
        assert await store.recent_suggestions(10) == []

    async def test_a_saved_report_is_read_back_verbatim(self, store):
        saved = await store.save_suggestions(
            "2026-10-12", "2026-10-12T08:55:00+07:00", '{"a": 1}', now=1000
        )

        assert saved.received_at == 1000
        assert await store.suggestions_on("2026-10-12") == saved
        assert saved.payload == '{"a": 1}'

    async def test_saving_the_same_date_again_replaces_the_report(self, store):
        await store.save_suggestions("2026-10-12", "t1", "old", now=1000)
        await store.save_suggestions("2026-10-12", "t2", "new", now=2000)

        [only] = await store.recent_suggestions(10)
        assert (only.generated_at, only.payload, only.received_at) == ("t2", "new", 2000)

    async def test_latest_follows_the_trading_date_not_the_arrival_time(self, store):
        await store.save_suggestions("2026-10-12", "t", "monday", now=1000)
        await store.save_suggestions("2026-10-09", "t", "friday, delivered late", now=5000)

        latest = await store.latest_suggestions()

        assert latest is not None
        assert latest.date == "2026-10-12"

    async def test_recent_is_newest_first_and_limited(self, store):
        for day in ("2026-10-08", "2026-10-09", "2026-10-12"):
            await store.save_suggestions(day, "t", day, now=1)

        reports = await store.recent_suggestions(2)

        assert [r.date for r in reports] == ["2026-10-12", "2026-10-09"]
