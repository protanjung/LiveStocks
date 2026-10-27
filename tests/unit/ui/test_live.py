from livestocks.ui.components import interval_text
from livestocks.ui.live import guarded


class TestGuarded:
    async def test_failing_step_does_not_raise_into_the_timer(self):
        async def broken() -> None:
            raise RuntimeError("upstream down")

        await guarded("refresh", broken)()

    async def test_healthy_step_runs_every_time(self):
        calls: list[int] = []

        async def step() -> None:
            calls.append(1)

        run = guarded("refresh", step)
        await run()
        await run()

        assert len(calls) == 2

    async def test_failure_does_not_stop_the_next_tick(self):
        attempts: list[int] = []

        async def flaky() -> None:
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("first tick fails")

        run = guarded("refresh", flaky)
        await run()
        await run()

        assert len(attempts) == 2


class TestIntervalText:
    def test_one_hour_is_singular(self):
        assert interval_text(3600) == "hour"

    def test_several_hours_are_plural(self):
        assert interval_text(6 * 3600) == "6 hours"

    def test_under_an_hour_still_reads_as_one_hour(self):
        assert interval_text(60) == "hour"
