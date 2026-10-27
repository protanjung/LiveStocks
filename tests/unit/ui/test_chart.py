import re
from pathlib import Path

import pytest

from livestocks.ui.chart import COLORS, _pill, forecast_options
from livestocks.ui.financials import financial_options
from livestocks.ui.seasonals import seasonal_options

CSS = (Path(__file__).parents[3] / "src/livestocks/ui/static/app.css").read_text(encoding="utf-8")
CSS_KEYS = {
    "pos": "--pos",
    "neg": "--neg",
    "accent": "--accent",
    "surface": "--surface",
    "fg": "--fg",
    "muted": "--muted",
    "line": "--line",
    "on_accent": "--on-accent",
}


def _tokens(selector: str) -> dict[str, str]:
    block = re.search(rf"(?m)^{re.escape(selector)} \{{(.*?)\}}", CSS, re.S)
    assert block, selector
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", block.group(1)))


def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    lighter, darker = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class TestPaletteParity:
    @pytest.mark.parametrize(("dark", "selector"), [(True, ":root"), (False, "body.body--light")])
    def test_chart_colours_match_the_stylesheet(self, dark, selector):
        tokens = _tokens(selector)
        for key, var in CSS_KEYS.items():
            if key == "on_accent" or var in tokens:
                assert COLORS[dark][key].lower() == tokens[var].lower(), (dark, key)


class TestPillLabels:
    @pytest.mark.parametrize("dark", [True, False])
    @pytest.mark.parametrize("colour", ["pos", "neg", "accent"])
    def test_label_text_is_readable_on_its_colour(self, dark, colour):
        col = COLORS[dark]

        assert _contrast(col["on_accent"], col[colour]) >= 4.5, (dark, colour)

    def test_pill_text_follows_the_theme(self):
        dark_pill = _pill("Max", 1.0, COLORS[True]["pos"], COLORS[True])
        light_pill = _pill("Max", 1.0, COLORS[False]["pos"], COLORS[False])

        assert dark_pill["rich"]["a"]["color"] == COLORS[True]["on_accent"]
        assert light_pill["rich"]["a"]["color"] == COLORS[False]["on_accent"]


class TestChartAccessibility:
    def test_forecast_chart_is_described_to_assistive_technology(self, make_forecast):
        options = forecast_options([], make_forecast(), True, 0)

        assert options["aria"] == {"enabled": True}

    def test_financial_chart_is_described_to_assistive_technology(self, quote_data):
        from livestocks.crawler.quote_stream import parse_quote

        options = financial_options(parse_quote(quote_data).eps_fy, "eps", dark=True)

        assert options["aria"] == {"enabled": True}

    def test_seasonal_chart_is_described_to_assistive_technology(self):
        assert seasonal_options([], dark=True)["aria"] == {"enabled": True}
