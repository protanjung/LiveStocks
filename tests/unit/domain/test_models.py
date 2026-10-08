import pytest

from livestocks.domain import Extras, Period, RatingTone, TickerStatus, TrackedTicker, rating_label


class TestPeriod:
    def test_surprise_is_relative_to_the_estimate(self):
        assert Period("2026-Q2", 63.54, 58.17, True).surprise == pytest.approx(0.0923, abs=0.001)

    @pytest.mark.parametrize(
        "period",
        [Period("x", None, 1.0, False), Period("x", 1.0, None, True), Period("x", 1.0, 0.0, True)],
    )
    def test_surprise_is_none_without_both_sides(self, period):
        assert period.surprise is None


class TestExtras:
    def test_rating_counts_follow_strong_buy_to_strong_sell(self):
        extras = Extras(18, 2, 2, 0, 1, (), (), (), ())
        assert extras.rating_counts == [
            ("Strong buy", 18),
            ("Buy", 2),
            ("Hold", 2),
            ("Sell", 0),
            ("Strong sell", 1),
        ]

    def test_rating_counts_are_none_when_any_count_is_missing(self):
        assert Extras(18, None, 2, 0, 1, (), (), (), ()).rating_counts is None


class TestTrackedTicker:
    def test_pending_without_forecast_or_error(self, make_ticker):
        assert make_ticker(with_forecast=False).status is TickerStatus.PENDING

    def test_error_when_a_crawl_failed_but_retries_remain(self):
        failed = TrackedTicker("IDX", "X", None, 0, 1, 0, "boom", 1, False, None, None)
        assert failed.status is TickerStatus.ERROR

    def test_failed_when_marked_dead(self):
        dead = TrackedTicker("IDX", "X", None, 0, 1, 0, "boom", 5, True, None, None)
        assert dead.status is TickerStatus.FAILED

    def test_ok_with_forecast_and_upside_from_average_target(self, make_ticker):
        ticker = make_ticker()
        assert ticker.status is TickerStatus.OK
        assert ticker.upside == pytest.approx(3394 / 2310 - 1)
        assert ticker.key == "IDX:TLKM"


class TestRatingLabel:
    @pytest.mark.parametrize(
        ("mark", "label", "tone"),
        [
            (1.0, "Strong buy", RatingTone.BUY),
            (2.0, "Buy", RatingTone.BUY),
            (3.0, "Neutral", RatingTone.HOLD),
            (4.0, "Sell", RatingTone.SELL),
            (5.0, "Strong sell", RatingTone.SELL),
            (None, "No rating", RatingTone.NONE),
        ],
    )
    def test_bucket_cut_offs(self, mark, label, tone):
        assert rating_label(mark) == (label, tone)

    def test_tone_compares_equal_to_its_plain_string(self):
        assert rating_label(1.0)[1] == "buy"
