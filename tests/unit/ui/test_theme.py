from pathlib import Path

import livestocks.ui.theme as theme

STATIC = Path(theme.__file__).parent / "static"


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
