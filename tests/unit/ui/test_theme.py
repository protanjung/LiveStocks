import re
from pathlib import Path

import pytest

import livestocks.ui.theme as theme

STATIC = Path(theme.__file__).parent / "static"
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
SRC = Path(theme.__file__).parent

# Classes that come from NiceGUI or Quasar rather than app.css.
EXTERNAL_CLASSES = ("q-", "nicegui-", "body--")


def _block(css: str, selector: str) -> str:
    match = re.search(rf"(?m)^{re.escape(selector)} \{{(.*?)\}}", css, re.S)
    assert match, selector
    return match.group(1)


def _tokens(scope: str) -> dict[str, str]:
    return dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", scope))


def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    lighter, darker = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class TestFonts:
    def test_every_declared_face_ships_as_a_file(self):
        for family, slug, weight in theme.FONT_FACES:
            assert (STATIC / "fonts" / f"{slug}-latin-{weight}-normal.woff2").is_file(), family

    def test_head_declares_every_face_from_the_local_directory(self):
        for _, slug, weight in theme.FONT_FACES:
            assert f"{theme.FONT_DIR}/{slug}-latin-{weight}-normal.woff2" in theme.FONTS_HEAD

    def test_no_external_font_host_is_referenced(self):
        assert "googleapis" not in theme.FONTS_HEAD
        assert "gstatic" not in theme.FONTS_HEAD

    def test_fonts_are_shown_while_loading(self):
        assert theme.FONTS_HEAD.count("font-display: swap") == len(theme.FONT_FACES)

    def test_license_ships_with_the_fonts(self):
        assert (STATIC / "fonts" / "OFL.txt").is_file()


class TestStylesheet:
    def test_head_links_the_stylesheet_that_exists(self):
        assert theme.STYLESHEET in theme.STYLESHEET_HEAD
        assert (STATIC / "app.css").is_file()

    def test_no_single_selector_rule_is_declared_twice(self):
        selectors = re.findall(r"(?m)^([^\s@/}{][^{]*?)\s*\{", CSS)
        single = [s for s in selectors if "," not in s and not s.startswith(":root")]
        duplicates = sorted({s for s in single if single.count(s) > 1})
        assert duplicates == []

    @pytest.mark.parametrize(
        ("fg", "bg"),
        [
            ("--fg", "--bg"),
            ("--fg", "--surface-2"),
            ("--muted", "--surface-2"),
            ("--faint", "--surface-2"),
            ("--on-accent", "--accent"),
            ("--pos", "--surface"),
            ("--neg", "--surface"),
            ("--warn", "--surface"),
        ],
    )
    @pytest.mark.parametrize("scope", [":root", "body.body--light"])
    def test_text_meets_wcag_aa_in_both_themes(self, scope, fg, bg):
        block = _block(CSS, scope) if scope == ":root" else _block(CSS, "body.body--light")
        tokens = _tokens(block)
        # The surface tokens may be defined only in :root; fall back to it for the dark theme.
        fallback = _tokens(_block(CSS, ":root"))
        fg_hex = tokens.get(fg) or fallback[fg]
        bg_hex = tokens.get(bg) or fallback[bg]
        assert _contrast(fg_hex, bg_hex) >= 4.5, (scope, fg, bg)

    def test_every_class_used_by_the_builders_is_styled(self):
        used: set[str] = set()
        for path in SRC.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for literal in re.findall(r"""class=['"]([^'"{}]+)['"]""", text):
                used.update(literal.split())
            for literal in re.findall(r"""\.classes\(\s*["']([^"'{}]+)["']""", text):
                used.update(literal.split())
        missing = sorted(
            c
            for c in used
            if not c.startswith(EXTERNAL_CLASSES) and not re.search(rf"\.{re.escape(c)}\b", CSS)
        )
        assert missing == []
