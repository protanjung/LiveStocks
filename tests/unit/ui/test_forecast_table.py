from dataclasses import replace

import pytest

from livestocks.ui.components import forecast_table, sort_tickers


class TestSortTickers:
    def test_price_sorts_descending_by_default_direction(self, make_ticker):
        cheap = make_ticker("AAA")
        dear = make_ticker("BBB")
        rows = [
            replace(cheap, forecast=replace(cheap.forecast, price=100.0)),
            replace(dear, forecast=replace(dear.forecast, price=900.0)),
        ]

        ordered = sort_tickers(rows, "price", -1)

        assert [r.symbol for r in ordered] == ["BBB", "AAA"]

    def test_tickers_without_a_forecast_go_last(self, make_ticker):
        pending = make_ticker("ZZZ", with_forecast=False)
        ranked = make_ticker("AAA")

        ordered = sort_tickers([pending, ranked], "ticker", 1)

        assert [r.symbol for r in ordered] == ["AAA", "ZZZ"]

    def test_unknown_key_is_rejected(self, make_ticker):
        with pytest.raises(KeyError):
            sort_tickers([make_ticker()], "nope", 1)


class TestForecastTable:
    def test_nine_columns_with_scoped_headers(self, make_ticker):
        html = forecast_table([make_ticker()], "ticker", 1, frozenset(), 0)

        assert html.count('<th scope="col"') == 9

    def test_active_sort_column_announces_its_order(self, make_ticker):
        html = forecast_table([make_ticker()], "price", -1, frozenset(), 0)

        assert 'aria-sort="descending"' in html
        assert html.count("aria-sort") == 1

    def test_ticker_symbol_links_to_the_detail_page(self, make_ticker):
        html = forecast_table([make_ticker("TLKM")], "ticker", 1, frozenset(), 0)

        assert '<a href="/t/IDX/TLKM">TLKM</a>' in html
        assert 'data-href="/t/IDX/TLKM"' in html

    def test_failed_ticker_shows_one_message_spanning_its_value_columns(self, make_ticker):
        failed = replace(
            make_ticker("BAD", with_forecast=False),
            dead=True,
            last_error="no quote",
            fail_count=5,
        )

        html = forecast_table([failed], "ticker", 1, frozenset(), 0)

        assert 'colspan="7"' in html
        assert "gave up after 5 tries" in html

    def test_error_text_is_escaped(self, make_ticker):
        bad = replace(
            make_ticker("BAD", with_forecast=False),
            last_error="<img src=x>",
            fail_count=1,
        )

        html = forecast_table([bad], "ticker", 1, frozenset(), 0)

        assert "&lt;img src=x&gt;" in html
        assert "<img" not in html

    def test_pending_ticker_says_it_is_fetching(self, make_ticker):
        pending = make_ticker("NEW", with_forecast=False)

        html = forecast_table([pending], "ticker", 1, frozenset(), 0)

        assert "Fetching first forecast" in html

    def test_retry_only_appears_for_failing_tickers(self, make_ticker):
        healthy = make_ticker("OK")
        broken = replace(
            make_ticker("BAD", with_forecast=False), last_error="timeout", fail_count=1
        )

        html = forecast_table([healthy, broken], "ticker", 1, frozenset(), 0)

        assert html.count('data-act="retry"') == 1
        assert 'aria-label="Retry BAD"' in html

    def test_every_row_can_be_removed_by_name(self, make_ticker):
        html = forecast_table([make_ticker("TLKM")], "ticker", 1, frozenset(), 0)

        assert 'data-act="remove" data-key="IDX:TLKM" aria-label="Remove TLKM"' in html

    def test_busy_ticker_shows_fetching_instead_of_its_age(self, make_ticker):
        html = forecast_table([make_ticker("TLKM")], "ticker", 1, frozenset({"IDX:TLKM"}), 0)

        assert "fetching" in html
