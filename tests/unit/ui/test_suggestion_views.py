import json

import pytest

from livestocks.domain import SuggestionReport
from livestocks.ui.suggestions import (
    action_counts,
    action_pill,
    dashboard_card,
    day_label,
    items_of,
    parse_report,
    report_head,
    suggestion_table,
    when,
)


def row(ticker="BBRI", action="BUY", **fields):
    base = {
        "ticker": ticker,
        "name": f"{ticker} Tbk",
        "held": True,
        "action": action,
        "lots": 3 if action != "HOLD" else 0,
        "entry": {"low": 3070, "high": 3100, "price": 3090},
        "tp1": 3600,
        "tp2": 3850,
        "stop": 2990,
        "stop_pct": -3.2,
        "rr": 5.1,
        "post_trade_weight_pct": 12.4,
        "verified": True,
        "reason": "Below consensus target.",
    }
    base.update(fields)
    return base


DATA = {
    "date": "2026-10-12",
    "generated_at": "2026-10-12T08:55:00+07:00",
    "market": {"ihsg_last": 6093.75, "summary": "IHSG +1.04% to 6,093.75."},
    "suggestions": [row("TLKM", "HOLD"), row("ADRO", "SELL"), row("BBRI", "BUY")],
    "disclaimer": "Informational only.",
}


class TestParseReport:
    def test_payload_text_becomes_a_dictionary(self):
        report = SuggestionReport("2026-10-12", "t", 1, json.dumps(DATA))

        assert parse_report(report)["date"] == "2026-10-12"

    @pytest.mark.parametrize("text", ["not json", "[1, 2]", "null"])
    def test_anything_but_an_object_gives_an_empty_dictionary(self, text):
        assert parse_report(SuggestionReport("d", "t", 1, text)) == {}


class TestItems:
    def test_buy_comes_first_then_sell_then_hold(self):
        assert [r["ticker"] for r in items_of(DATA)] == ["BBRI", "ADRO", "TLKM"]

    def test_a_missing_or_malformed_list_gives_no_rows(self):
        assert items_of({}) == []
        assert items_of({"suggestions": "x"}) == []
        assert items_of({"suggestions": ["x", 1]}) == []

    def test_counts_cover_the_three_actions(self):
        assert action_counts(items_of(DATA)) == {"BUY": 1, "SELL": 1, "HOLD": 1}


class TestFormatting:
    @pytest.mark.parametrize(
        ("iso", "expected"),
        [
            ("2026-10-12T08:55:00+07:00", "12 Oct 2026, 08:55 WIB"),
            ("2026-10-12T01:55:00+00:00", "12 Oct 2026, 01:55 UTC"),
            ("2026-10-12T08:55:00+05:30", "12 Oct 2026, 08:55 UTC+05:30"),
            (None, "—"),
            ("yesterday", "yesterday"),
        ],
    )
    def test_generated_time_names_its_zone(self, iso, expected):
        assert when(iso) == expected

    def test_trading_dates_read_as_weekday_and_day(self):
        assert day_label("2026-10-12") == "Mon 12 Oct"
        assert day_label("soon") == "soon"

    def test_actions_use_the_tone_classes(self):
        assert 'class="rate buy"' in action_pill("BUY")
        assert 'class="rate sell"' in action_pill("SELL")
        assert 'class="rate hold"' in action_pill("HOLD")


class TestTable:
    def test_levels_and_reason_are_shown(self):
        html = suggestion_table(items_of(DATA))

        for text in (
            "BBRI",
            "3,090",
            "3,600",
            "3,850",
            "2,990",
            "−3.2%",
            "1 : 5.1",
            "Below consensus",
        ):
            assert text in html

    def test_hold_rows_show_no_lots_and_unverified_rows_are_flagged(self):
        hold = row("TLKM", "HOLD", verified=False, entry={"low": None, "high": None, "price": None})

        html = suggestion_table([hold])

        assert "unverified" in html
        assert '<td class="r num">—</td>' in html

    def test_text_from_the_report_is_escaped(self):
        html = suggestion_table([row(reason="<script>alert(1)</script>", name="A & B")])

        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "A &amp; B" in html

    def test_empty_report_says_so(self):
        assert "no stock rows" in suggestion_table([])


class TestCards:
    def test_head_shows_ihsg_summary_and_counts(self):
        html = report_head(DATA, received_at=1000, now=1000 + 3600)

        assert "IHSG 6,093.75" in html
        assert "IHSG +1.04%" in html
        assert "1 BUY" in html
        assert "stored 1 h ago" in html

    def test_dashboard_card_lists_only_buys_and_sells_and_links_to_the_page(self):
        html = dashboard_card(DATA, "2026-10-12", received_at=1000, now=1000)

        assert "BBRI" in html
        assert "ADRO" in html
        assert "TLKM" not in html
        assert 'href="/suggestions"' in html

    def test_dashboard_card_without_moves_says_to_hold(self):
        html = dashboard_card({"suggestions": [row("TLKM", "HOLD")]}, "2026-10-12", 1, now=1)

        assert "Hold everything" in html
